import zmq

context = zmq.Context()

# Create PULLER to receive information from processor instances
receiver = context.socket(zmq.PULL)
receiver.bind("tcp://*:5561")

# Create PUBLISHER to send information back to Workstations
sender = context.socket(zmq.PUB)
sender.bind("tcp://*:5562")

while True:
    s = receiver.recv()
    sender.send(s)
