# -*- coding: utf-8 -*-
"""Transformer Discriminator Models

- First model has one input layer. This model can be used/adapted for any sequence classification task.
(e.g. sentiment analysis, topic attribution, NER, etc.)

- Second model (transformer discriminator 2) has 2 input layers, which means it can be used
in tasks where the network needs to see two input sequences at a time (e.g. french and english)
and then decide whether the sequences belong to certain classes. (e.g. if appropriate translation or not).

Written by Niloy Purkait for GSoC
"""

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import tensorflow_datasets as tfds
import time
import numpy as np


"""## Implement multi head self attention as a Keras layer"""

class MultiHeadSelfAttention(layers.Layer):
    def __init__(self, embed_dim, num_heads=8):
        super(MultiHeadSelfAttention, self).__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        if embed_dim % num_heads != 0:
            raise ValueError(
                f"embedding dimension = {embed_dim} should be divisible by number of heads = {num_heads}"
            )
        self.projection_dim = embed_dim // num_heads
        self.query_dense = layers.Dense(embed_dim)
        self.key_dense = layers.Dense(embed_dim)
        self.value_dense = layers.Dense(embed_dim)
        self.combine_heads = layers.Dense(embed_dim)

    def attention(self, query, key, value):
        score = tf.matmul(query, key, transpose_b=True)
        dim_key = tf.cast(tf.shape(key)[-1], tf.float32)
        scaled_score = score / tf.math.sqrt(dim_key)
        weights = tf.nn.softmax(scaled_score, axis=-1)
        output = tf.matmul(weights, value)
        return output, weights

    def separate_heads(self, x, batch_size):
        x = tf.reshape(x, (batch_size, -1, self.num_heads, self.projection_dim))
        return tf.transpose(x, perm=[0, 2, 1, 3])

    def call(self, inputs):
        # x.shape = [batch_size, seq_len, embedding_dim]
        batch_size = tf.shape(inputs)[0]
        query = self.query_dense(inputs)  # (batch_size, seq_len, embed_dim)
        key = self.key_dense(inputs)  # (batch_size, seq_len, embed_dim)
        value = self.value_dense(inputs)  # (batch_size, seq_len, embed_dim)
        query = self.separate_heads(
            query, batch_size
        )  # (batch_size, num_heads, seq_len, projection_dim)
        key = self.separate_heads(
            key, batch_size
        )  # (batch_size, num_heads, seq_len, projection_dim)
        value = self.separate_heads(
            value, batch_size
        )  # (batch_size, num_heads, seq_len, projection_dim)
        attention, weights = self.attention(query, key, value)
        attention = tf.transpose(
            attention, perm=[0, 2, 1, 3]
        )  # (batch_size, seq_len, num_heads, projection_dim)
        concat_attention = tf.reshape(
            attention, (batch_size, -1, self.embed_dim)
        )  # (batch_size, seq_len, embed_dim)
        output = self.combine_heads(
            concat_attention
        )  # (batch_size, seq_len, embed_dim)
        return output

"""## Implement a Transformer block as a layer"""

class TransformerBlock(layers.Layer):
    def __init__(self, embed_dim, num_heads, ff_dim, rate=0.1):
        super(TransformerBlock, self).__init__()
        self.att = MultiHeadSelfAttention(embed_dim, num_heads)
        self.ffn = keras.Sequential(
            [layers.Dense(ff_dim, activation="relu"), layers.Dense(embed_dim),]
        )
        self.layernorm1 = layers.LayerNormalization(epsilon=1e-6)
        self.layernorm2 = layers.LayerNormalization(epsilon=1e-6)
        self.dropout1 = layers.Dropout(rate)
        self.dropout2 = layers.Dropout(rate)

    def call(self, inputs, training):
        attn_output = self.att(inputs)
        attn_output = self.dropout1(attn_output, training=training)
        out1 = self.layernorm1(inputs + attn_output)
        ffn_output = self.ffn(out1)
        ffn_output = self.dropout2(ffn_output, training=training)
        return self.layernorm2(out1 + ffn_output)

"""## Implement embedding layer
Two seperate embedding layers, one for tokens, one for token index (positions).
"""

class TokenAndPositionEmbedding(layers.Layer):
    def __init__(self, maxlen, vocab_size, embed_dim):
        super(TokenAndPositionEmbedding, self).__init__()
        self.token_emb = layers.Embedding(input_dim=vocab_size, output_dim=embed_dim)
        self.pos_emb = layers.Embedding(input_dim=maxlen, output_dim=embed_dim)

    def call(self, x):
        maxlen = tf.shape(x)[-1]
        positions = tf.range(start=0, limit=maxlen, delta=1)
        positions = self.pos_emb(positions)
        x = self.token_emb(x)
        return x + positions


"""## Model 1 : Sees concatenated input target pairs
"""

def TransformerDiscriminator(vocab_size, maxlen = 500,
                             embed_dim = 32,  # Embedding size for each token
                             num_heads = 2 ,  # Number of attention heads
                             ff_dim = 32):    # # Hidden layer size in feed forward network inside transformer

    #vocab_size = tokenizer_txt.vocab_size+2  # Only consider the top 20k words
    #maxlen = 500  # Only consider the first 200 words of each movie review


    inputs = layers.Input(shape=(maxlen,))
    embedding_layer = TokenAndPositionEmbedding(maxlen, vocab_size, embed_dim)
    x = embedding_layer(inputs)
    transformer_block = TransformerBlock(embed_dim, num_heads, ff_dim)
    x = transformer_block(x)
    x = layers.GlobalAveragePooling1D()(x)
    x = layers.Dropout(0.1)(x)
    x = layers.Dense(20, activation="relu")(x)
    x = layers.Dropout(0.1)(x)
    outputs = layers.Dense(1, activation="sigmoid")(x)

    model = keras.Model(inputs=inputs, outputs=outputs)

    model.summary()

    return model



"""## Model 2 : Sees input triples and text via two seperate input layers
"""


def TransformerDiscriminator2(vocab_size, maxlen = 500,
                             embed_dim = 32,  # Embedding size for each token
                             num_heads = 2 ,  # Number of attention heads
                             ff_dim = 32):    # # Hidden layer size in feed forward network inside transformer

    #vocab_size = tokenizer_txt.vocab_size+2  # Only consider the top 20k words
    #maxlen = 500  # Only consider the first 200 words of each movie review


    inputs_rdf = layers.Input(shape=(maxlen,), name='rdf')
    inputs_txt = layers.Input(shape=(maxlen,), name='txt')
    
    embedding_layer = TokenAndPositionEmbedding(maxlen, vocab_size, embed_dim)
    
    x_rdf = embedding_layer(inputs_rdf)
    x_txt = embedding_layer(inputs_txt)

    
    transformer_block = TransformerBlock(embed_dim, num_heads, ff_dim)
    
    x_rdf = transformer_block(x_rdf)
    x_rdf = layers.GlobalAveragePooling1D()(x_rdf)
    x_rdf = layers.Dropout(0.1)(x_rdf)

    x_txt = transformer_block(x_txt)
    x_txt = layers.GlobalAveragePooling1D()(x_txt)
    x_txt = layers.Dropout(0.1)(x_txt)

    x = layers.concatenate([x_rdf, x_txt])

    x = layers.Dense(20, activation="relu")(x)
    x = layers.Dropout(0.1)(x)
    outputs = layers.Dense(1, activation="sigmoid", name='real_prob')(x)

    model = keras.Model(inputs=[inputs_rdf, inputs_txt], outputs=outputs)

    model.summary()


    return model
