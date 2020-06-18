import numpy as np
from tqdm import tqdm
import json
import os
import tensorflow as tf
import skimage.io as io
from sklearn.model_selection import train_test_split

K = tf.keras
VGG_FEATURES = 4096
VOCAB_SIZE = 1000
MAX_LEN = 20


class DataLoader:
    def __init__(self):
        pass

    @staticmethod
    def load_data():
        with open('captions.json', 'r') as f:
            anns = json.load(f)

        tokenizer = K.preprocessing.text.Tokenizer(num_words=VOCAB_SIZE)

        tlist = []
        for _, v in anns.items():
            for el in v:
                tlist.append(el)
        tokenizer.fit_on_texts(tlist)

        x = []
        y = []
        for k, v in tqdm(anns.items()):
            img_path = os.path.join('coco_data', '{}.png'.format(str(k).zfill(20)))
            img = io.imread(img_path)

            if np.shape(img) != (224, 224, 3):
                continue

            for ann in v:
                x.append(img)
                seq = tokenizer.texts_to_sequences([ann])[0]
                y.append(K.preprocessing.sequence.pad_sequences([seq], maxlen=MAX_LEN, padding='post')[0])

        # return train_test_split(x, y, test_size=0.2, random_state=42)

        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)

        # for i in range(len(x_train)):
        #     x_train[i] = [x_train[i], y_train[i]]

        return np.asarray(x_train), np.asarray(x_test), np.asarray(y_train), np.asarray(y_test)


class ImageCaptioner:
    def __init__(self, hidden_size, dropout):
        self.hidden_size = hidden_size
        self.dropout = dropout

        self.cnn = self.build_cnn_model()
        self.lstm = self.build_lstm_weights()

    def get_model(self):
        inp_img = K.Input((224, 224, 3))
        inp_captions = K.Input((MAX_LEN,))

        return K.Model(inputs=[inp_img, inp_captions], outputs=self.fprop(inp_img, inp_captions, ver='train'))

    def fprop(self, img, captions=None, ver='test'):
        assert ver in ['train', 'test']

        features = self.get_features(img)
        if ver == 'train':
            assert captions is not None
            out = self.training_generate_captions(features, captions)
        else:
            out = self.testing_generate_captions(features)

        return out

    def get_features(self, x):
        vgg_features = self.cnn(x, training=False)
        vec = K.layers.Dense(self.hidden_size, activation='relu')(vgg_features)
        return vec

    def training_generate_captions(self, features, captions):
        captions = captions[:, :-1]
        embed_cap = self.lstm['embed'](captions)
        features = tf.expand_dims(features, axis=1)
        inp = tf.concat([features, embed_cap], axis=1)

        hidden_out, _, _ = self.lstm['lstm_cells'](inp)
        final_out = self.lstm['dense_out'](hidden_out)

        return final_out

    def testing_generate_captions(self, features):
        output_sentence = []
        hidden, cell = None, None

        for i in range(MAX_LEN):
            embed = features if len(output_sentence) == 0 else self.lstm['embed'](output_sentence[-1])
            _, new_hidden, new_cell = self.lstm['lstm_cells'](embed, initial_state=[hidden, cell])
            hidden, cell = new_hidden, new_cell

            dense_out = self.lstm['dense_out'](new_hidden)
            output_sentence.append(tf.argmax(dense_out, axis=1))

        return output_sentence

    @staticmethod
    def build_cnn_model():
        vgg = K.applications.vgg16.VGG16()
        model = K.Model(inputs=vgg.inputs, outputs=vgg.layers[-2].output)

        for layer in model.layers:
            layer.trainable = False

        return model

    def build_lstm_weights(self):
        ret = {
            'embed': K.layers.Embedding(VOCAB_SIZE, self.hidden_size, mask_zero=True),
            'lstm_cells': K.layers.LSTM(self.hidden_size, return_sequences=True, return_state=True),
            'dense_out': K.layers.TimeDistributed(K.layers.Dense(VOCAB_SIZE, activation='softmax'))
        }

        return ret


def main():
    cap = ImageCaptioner(hidden_size=256, dropout=0.2)
    x_train, x_test, y_train, y_test = DataLoader.load_data()
    print(np.shape(x_train))
    print(np.shape(y_train))

    model = cap.get_model()
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    print(model.summary())

    model.fit([x_train, y_train], y_train, batch_size=32, epochs=10)


if __name__ == '__main__':
    main()