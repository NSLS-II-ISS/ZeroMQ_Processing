import zmq

context = zmq.Context()

# Create PULLER to receive information from clients (workstations)
receiver = context.socket(zmq.PULL)
receiver.bind("tcp://*:5559")

# Create PUSHER to send information to workers (instances on xf08id-srv1)
sender = context.socket(zmq.PUSH)
sender.bind("tcp://*:5560")

while True:
    s = receiver.recv()
    sender.send(s)
