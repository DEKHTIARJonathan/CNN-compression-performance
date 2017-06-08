"""
This script takes in input a pb file, restores the weights of the network, and then computes the ranges for each layer
"""
import argparse
import numpy as np
import tensorflow as tf
from tensorflow.contrib.util import make_ndarray


def get_weights_from_pb(pb_file):
    """
    takes in input a pb file, restores the weights of the network, and returns a list containing a ndarray with the
    weights and the biases for each layer
    :param pb_file: path to the pb file of the network
    :return: a list containing for each layer a ndarray with its parameters
    """
    with tf.gfile.GFile(pb_file, "rb") as f:
        graph_def = tf.GraphDef()
        graph_def.ParseFromString(f.read())
        # get all the weights tensor as ndarray
        weights = [make_ndarray(node_def.attr['value'].tensor)
                   for node_def in graph_def.node
                   if node_def.attr['value'].tensor.dtype is not 0 and 'Variable' in node_def.name]
        # flatten the elements in weights
        weights = [sum(el.tolist(), []) for el in weights]
    print weights
    return [np.concatenate(ws, bs)
            for ws in [weights[i] for i in range(0, len(weights), 2)]
            for bs in [weights[i] for i in range(1, len(weights), 2)]]


def get_ranges(weights):
    """

    :param weights: a list containing the parameters for each layer
    :return: a list of tuple (min, max) for each layer
    """
    return [(params.min(), params.max()) for params in weights]


help = 'This script takes in input a pb file, restores the weights of the network, and then computes the ranges for ' \
       'each layer '

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=help)
    parser.add_argument('--pb_file', type=str, nargs=1, help='pb file containing a neural network')
    args = parser.parse_args()
    weights = get_weights_from_pb(args.pb_file[0])
    print get_ranges(weights)
