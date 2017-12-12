import zmq
import json
import socket
from threading import Thread
import time as ttime
import pandas as pd

import matplotlib.pyplot as plt
plt.ion()

context = zmq.Context()
sender = context.socket(zmq.PUSH)
sender.connect("tcp://xf08id-srv1:5559")

# Create SUBSCRIBER to get information from 'gateway'
subscriber = context.socket(zmq.SUB)
subscriber.connect("tcp://xf08id-srv1:5562")

hostname_filter = socket.gethostname()

subscriber.setsockopt_string(zmq.SUBSCRIBE, hostname_filter)


def recv_function():
    while True:
        message = subscriber.recv().decode('utf-8')
        message = message[len(hostname_filter):]
        data = json.loads(message)
        if data['type'] == 'spectroscopy':
            if data['processing_ret']['type'] == 'interpolate':
                interp_data = pd.DataFrame.from_dict(json.loads(data['processing_ret']['data']))
                interp_data = interp_data.sort_values('energy')

                #plt.figure()
                #plt.plot(interp_data['energy'], interp_data['i0']/interp_data['it'])
                #plt.figure()
                #plt.plot(interp_data['energy'], interp_data['iff']/interp_data['i0'])

                # plot on interpolation plot and generate log

recv_thread = Thread(target = recv_function)
recv_thread.start()

dic = {'uid': '61d3b7f0-9c9d-4e19-b08c-6229c2473123',
       'requester': hostname_filter,
       'type': 'spectroscopy',
       'processing_info': {'type': 'interpolate',
                           'interp_base': 'i0'
                          }
      }

#sender.send_string(json.dumps(dic))


#while True:
#    pass

