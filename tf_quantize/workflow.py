import argparse
import subprocess, signal, platform, os
from net_perf.net_performance import NetPerformance
from datetime import datetime
import tensorflow as tf
from tensorflow.python.tools import freeze_graph
import importlib
from distutils.util import strtobool
import json

from pattern.pattern import ToBeQuantizedNetwork

help = 'This script takes as input a cnn implemented using tensorflow. The network have to be defined like the in the' \
       'example file mnist_patter_implemementation.py, extending the ToBeQuantizedNetwork abstract class in ' \
       'pattern.py. It calls the prepare and train methods on the network. The implementation of the network need ' \
       'also to export the variables and the metagraph in the training method using the tf api. This script then take ' \
       'the files and obtains a pb file description of the network, needed to quantize it. The net is quantized and ' \
       'then the performance of the original network and the quantized one are compared in terms of accuracy, ' \
       'execution time, and cache misses.'

# performance events
perf_ev_list = ['cache-misses', 'cache-references', 'L1-dcache-load-misses', 'L1-dcache-loads', 'L1-dcache-stores',
                'LLC-load-misses', 'LLC-loads', 'LLC-store-misses', 'LLC-loads']


def quantize(model):
    """
    Quantize the graph
    quantize takes the model of the net. output graph name is the output of the method freeze.
    output name is the name of the output node of the net
    quantized graph name is the output of the method quantize.
    requires an env variable pointing to the tensorflow home like ~/dev/tensorflow
    :param model: the net implementing the abstract class
    """
    quantize_command = os.environ['TF_HOME'] + '/bazel-bin/tensorflow/tools/quantization/quantize_graph \
  --input=' + model.output_pb_path + ' \
  --output_node_names="' + model.output_node_name + '" --output=' + model.output_quantized_graph + ' \
  --mode=eightbit'
    process = subprocess.Popen(quantize_command, shell=True, stdout=subprocess.PIPE)
    process.wait()


def export_to_pb(model):
    """
    This method export to pb the network defined in the model param. The train have to be already done and the
    variables and the meta graph have to be already exported. The method assumes that the path of the meta graph file
    is model.metagraph_path and the checkpoint have been stored with the model.checkpoint_prefix. The output file will
    be stored with model.output_pb_path
    :param model: an instance of a ToBeQuantizedNetwork subclass
    """
    input_graph_name = model.metagraph_path
    output_graph_name = model.output_pb_path

    input_saver_def_path = ""
    input_binary = False
    input_checkpoint_path = model.checkpoint_prefix
    output_node_names = model.output_node_name
    restore_op_name = tf.train.latest_checkpoint(model.checkpoint_prefix)
    filename_tensor_name = "save/Const:0"
    clear_devices = True

    freeze_graph.freeze_graph(input_graph_name, input_saver_def_path,
                              input_binary, input_checkpoint_path,
                              output_node_names, restore_op_name,
                              filename_tensor_name, output_graph_name, clear_devices, "")


def cache_perf_test(function_to_call, *args):
    """
    Runs the function passed as argument inside perf tool. perf writes inside the stderr
    -x command is to format output is csv style
    -e command is for event stats
    -p command is to attach perf to the process with specified pid
    :param function_to_call: is a function to call, function are first order obj in python
    :param args: arguments required from function to call
    :return: the performance of the net
    """
    print 'Running on ' + platform.system()
    if platform.system() == 'Linux':
        print 'Testing the model'
        ev_list = ','.join(perf_ev_list)
        perf_command = 'perf stat -x, -e ' + ev_list + ' -p' + str(os.getpid())
        # with shell = true the shell is the process and the commands are the child
        # if shell false the command must be splitted and it's the process
        process = subprocess.Popen(perf_command.split(" "), shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        acc = function_to_call(*args)
        process.send_signal(signal.SIGINT)
        print 'Terminated, accuracy =' + str(acc)
        out, err = process.communicate()
        print err
        return acc, err
    else:
        print 'Perf in not available, testing without cache performance'
    acc = function_to_call(*args)
    return acc, ""


def get_test_time(function_to_call, *args):
    """
    Get the duration of the function_to_call parameter
    :param function_to_call: function to test
    :param args: arguments needed from the function
    :return: The duration in seconds of the function to call
    """
    init_time = datetime.now()
    function_to_call(*args)
    final_time = datetime.now()
    duration = final_time - init_time
    return duration.total_seconds()


def get_model_perf(function_to_call, net_name, test_data, *args):
    """
    Test the performance of the function to call in terms of cache and time
    :param function_to_call: is a function that takes as input *args, is the function that evaluates the model and gets benchmarked
    :param net_name: the name of the net
    :param test_data: The tensor containing the test data, in order to get the avg forward time
    :param args:  arguments needed from the function to call
    :return: a NetPerformance object containing the performance of the net
    """
    # get cache performance
    acc, perf_stdout = cache_perf_test(function_to_call, *args)
    net_perf = NetPerformance(net_name,float(acc), perf_stdout)
    # get test time
    # get test size, test_data is not a tensor, convert it with convert_to_tensor and get its shapes
    # shape[0] is the number of items, shape[1] is product of number of pixel I think
    test_data_size = tf.convert_to_tensor(test_data).get_shape()[0].value
    # convert time returned by get test time into time for each item, in this way we get the average time
    net_perf.test_time = get_test_time(function_to_call, *args) / test_data_size
    print net_perf
    return net_perf


def evaluate(output_node, test_data, labels, input_placeholder_node, label_placeholder_node, graph):
    """
    Takes a graph as input, attaches an accuracy node and evaluates it. Notice that the tensor must be created
    in the same graph of output node, with graph.as_default()
    :param output_node output node of the net, used for accuracy
    :param labels is the tensor containing labels of test data
    :param input_placeholder_node node used for placeholder for input
    :param label_placeholder_node node used as placeholder for labels
    :param test_data test images
    :param graph is the graph of the output node
    :return: the accuracy of the net
    """
    with graph.as_default():
        sess = tf.Session(graph=graph)
        correct_prediction = tf.equal(tf.argmax(output_node, 1), tf.argmax(labels, 1))
        accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
        acc = sess.run(accuracy,
                       feed_dict={input_placeholder_node: test_data,
                                  label_placeholder_node: labels})
        return acc


def restore(meta_graph_path, model):
    """
    Takes a pb path of a freezed graph and restores it. :0 after the name is to get the first of the list. Graph is
    needed because tensor must belong to the same graph.
    #TODO Label placehoder are created directly here, we must be
    parametric in some way...
    :param model is an instance of the abstract class
    :param meta_graph_path is the path of the freezed graph
    :return: (ouput_node,input_placeholder,label_placeholder,graph)
    """
    # We load the protobuf file from the disk and parse it to retrieve the
    # unserialized graph_def
    with tf.gfile.GFile(meta_graph_path, "rb") as f:
        graph_def = tf.GraphDef()
        graph_def.ParseFromString(f.read())

    # Then, we can use again a convenient built-in function to import a graph_def into the 
    # current default Graph
    with tf.Graph().as_default() as graph:
        tf.import_graph_def(
            graph_def,
            input_map=None,
            return_elements=None,
            op_dict=None,
            name="prefix",
            producer_op_list=None
        )

        # access placeholder
        input_placeholder = graph.get_tensor_by_name("prefix/" + model.input_placeholder_name + ":0")
        # create label placeholder
        label_placeholder = tf.placeholder(tf.float32, shape=[None, 10], name="labels")
        # get output node
        output_node = graph.get_tensor_by_name("prefix/" + model.output_node_name + ":0")

        return output_node, input_placeholder, label_placeholder, graph


def main(model, to_train, to_quantize, to_evaluate):
    model.prepare()
    if to_train:
        model.train()
    print "Exporting the graph"
    # export the trained model to pb
    export_to_pb(model)
    # quantize the trained model
    if to_quantize:
        quantize(model)
    # restore the real model
    if to_evaluate:
        output_node, input_placeholder, label_placeholder, graph = restore(model.output_pb_path, model)
        # get performance of the model
        original_net_perf = get_model_perf(evaluate, model.net_name, model.test_data[0], output_node,
                                           model.test_data[0], model.test_data[1], input_placeholder,
                                           label_placeholder, graph)
        original_net_perf.quantized = False
        original_net_perf.path = model.output_pb_path
        original_net_perf.size = os.path.getsize(model.output_pb_path)
        # the same with the quantized model
        output_node, input_placeholder, label_placeholder, graph = restore(model.output_quantized_graph, model)
        quantized_net_perf = get_model_perf(evaluate, model.net_name+'_quant', model.test_data[0], output_node,
                                            model.test_data[0], model.test_data[1], input_placeholder,
                                            label_placeholder, graph)
        quantized_net_perf.quantized = True
        # set the size of the pb
        quantized_net_perf.size = os.path.getsize(model.output_quantized_graph)
        # set the path of the pb
        quantized_net_perf.path = model.output_quantized_graph
        # print on a file the networks
        f = open(model.checkpoint_prefix + '_' + model.net_name + '_performance', 'w')
        json.dump([original_net_perf.__dict__, quantized_net_perf.__dict__], f, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=help)
    parser.add_argument('--module_name', type=str, nargs=1, help='python file containing an implementation of '
                                                                 'ToBeQuantizedNetwork')
    parser.add_argument('--class_name', type=str, nargs=1, help='the name of the class')
    parser.add_argument('--train', type=str, nargs=1, help='True if you want to train, false otherwise. If you say '
                                                           'false you need to have already a metagraph and a '
                                                           'checkpoint')
    parser.add_argument('--quantize', type=str, nargs=1, help='True if you want to quantize the net, false otherwise')
    parser.add_argument('--evaluate', type=str, nargs=1, help='True if you want to evauate the network(s)')
    args = parser.parse_args()
    user_module = importlib.import_module(args.module_name[0])
    user_class = getattr(user_module, args.class_name[0])
    # raises an exception if the input class does not satisfies to ToBeQuantized requirements
    ToBeQuantizedNetwork.register(user_class)
    model_instance = user_class()
    main(model_instance, strtobool(args.train[0]), strtobool(args.quantize[0]), strtobool(args.evaluate[0]))
