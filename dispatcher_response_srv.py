import zmq
import socket

context = zmq.Context()
machine_name = socket.gethostname()

###### Set up logging.
import logging
import logging.handlers
logger = logging.getLogger('dispatcher_srv')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# Write DEBUG and INFO messages to /var/log/data_processing_worker/debug.log.
debug_file = logging.handlers.RotatingFileHandler(
    '/nsls2/xf08id/log/{}_data_processing_debug.log'.format(machine_name),
    maxBytes=10000000, backupCount=9)
debug_file.setLevel(logging.DEBUG)
debug_file.setFormatter(formatter)
logger.addHandler(debug_file)
# Write INFO messages to /var/log/data_processing_worker/info.log.
info_file = logging.handlers.RotatingFileHandler(
    '/nsls2/xf08id/log/{}_data_processing_info.log'.format(machine_name),
    maxBytes=10000000, backupCount=9)
info_file.setLevel(logging.INFO)
info_file.setFormatter(formatter)
logger.addHandler(info_file)
###### Doneet up logging.


# Create PULLER to receive information from processor instances
receiver = context.socket(zmq.PULL)
receiver.bind("tcp://*:5561")

# Create PUBLISHER to send information back to Workstations
sender = context.socket(zmq.PUB)
sender.bind("tcp://*:5562")

while True:
    s = receiver.recv()
    logger.info("Received a request to plot. Sending...")
    sender.send(s)
    logger.info("Sent.")
