import caffe
import argparse
import configparser
import sys
import os
import subprocess 

from utility.solver_reader import SolverReader

#
# train the network, you will find the weights files as in the definition of the
# snapshot_prefix in the solver .prototxt file
#
def train(solver_filename):
	solver = caffe.SGDSolver(str(solver_filename))
	caffe.set_mode_cpu()
	solver.solve()

#
# compress the network using the passed method, the output files will be in the
# net directory
#
def compress(solver_filename, mode, error_margin=1, iterations=1000):
	solver_reader = SolverReader(solver_filename) # the working directory is the one containing the solver.prototxt
	net = solver_reader.solver.net
	max_iter = solver_reader.solver.max_iter
	weights = solver_reader.weightsFilename()
	output = solver_reader.compressionOutputFilename(mode)
	# build the ristretto command
	command = os.environ['RISTRETTOPATH'] + "/build/tools/ristretto quantize" + "\
		--model=" + net + "\
		--weights=" + weights + "\
		--model_quantized=" + output + "\
		--iterations=" + iterations + "\
		--trimming_mode=" + mode + "\
		--error_margin=" + error_margin	
	process = subprocess.Popen(command, shell=True, stdout = subprocess.PIPE)
	process.wait()

#
# create the new solver file and call train
#
def fine_tune(solver_filename, compression_mode):
	# create a new solver file, equal to the input
	# but with compressed network as target
	solver_reader = SolverReader(solver_filename)
	fine_tune_solver_file = solver_reader.createFineTuneSolverFile(compression_mode)
	train(fine_tune_solver_file)

#
# obtain the name of the net and the name of the weights file
# from the solver file and call valgrind 
#
def test(solver_filename, test_iterations,performance_path):
	solver_reader = SolverReader(solver_filename)
	net = solver_reader.solver.net
	weights = solver_reader.weightsFilename()
	# create the folder if not exists
	if not os.path.exists(performance_path):
		os.mkdir(performance_path)
	# create the output file for valgrind
	cachegrind_out_file = performance_path + '/' + net.split('.')[0] + '_cachegrind.txt'
	# create the output file
	command = "valgrind --tool=cachegrind \
		--cachegrind-out-file=" + cachegrind_out_file + "\
		$RISTRETTOPATH/build/tools/caffe test \
		-model=" + net + "\
		-weights=" + weights + "\
		-iterations=" + str(test_iterations)	
	process = subprocess.Popen(command, shell=True, stdout = subprocess.PIPE)
	process.wait()


if __name__ == "__main__":
	# get the config file as parameter
	arg_parser = argparse.ArgumentParser(description='TODO')#TODO
	arg_parser.add_argument('ini_file', nargs=1, type = str)
	args = arg_parser.parse_args()

	# parse the config file
	config = configparser.ConfigParser()
	config.read(args.ini_file[0])
	to_train = config['CAFFE'].getboolean('train')
	solver_path = config['CAFFE']['solver_path']
	error_margin = config['RISTRETTO']['error_margin']
	iterations = config['RISTRETTO']['iterations']
	test_iterations = config['TEST']['iterations']
	performance = config['TEST'].getboolean('performance')
	performance_path = config['TEST']['performance_path']

	# go in the directory of the solver
	os.chdir(os.path.dirname(solver_path))
	solver_filename = solver_path.split('/')[len(solver_path.split('/'))-1]
	print solver_filename
	print os.getcwd()

	# train the input net
	if to_train:
		train(solver_filename)

	# compress the net with the modes in the ini file and fine tune
	for compression_mode in ('dynamic_fixed_point', 'minifloat', 'integer_power_of_2_weights'):
		if config['RISTRETTO'][compression_mode]:
			compress(solver_filename, compression_mode, error_margin, iterations)
			fine_tune(solver_filename, compression_mode)

	# run the test through valgrind for the non compressed network
	if performance:
		test(solver_filename, test_iterations,performance_path)
		solver_reader = SolverReader(solver_filename)
		for compression_mode in ('dynamic_fixed_point', 'minifloat', 'integer_power_of_2_weights'):
			if config['RISTRETTO'][compression_mode]:
				fine_tune_solver = solver_reader.fineTuneSolverName(compression_mode)
				test(fine_tune_solver, test_iterations,performance_path)

