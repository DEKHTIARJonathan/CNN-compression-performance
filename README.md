# Introduction

For real world application, convolutional neural network(CNN) model can take more than 100MB of space and can be computationally too expensive. Therefore, there are multiple methods to reduce this complexity in the state of art. Ristretto is a plug-in to Caffe framework that employs several model approximation methods. For this projects, ﬁrst a CNN model will be trained for Cifar-10 dataset with Caffe, then Ristretto will be use to generate multiple approximated version of the trained model using different schemes. The goal of this projects is comparison of the models in terms of execution performance, model size and cache utilizations in the test or inference phase.
The same steps are done with Tensorflow and Quantisation tool. The quantisation schemes of Tensorflow and Ristretto are then compared.

# Folder description

- ristretto: contains the tools for caffe ristretto quantization
- tf_quantize: contains the tools for tensorflow quantization

A more detailed description is inside the readme of each folder.

# Authors

- Emanuele Ghelfi
- Emiliano Gagliardi
