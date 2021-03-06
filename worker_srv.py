# Set up a Broker.
from databroker import Broker
db = Broker.named('iss')
db_analysis = Broker.named('iss-analysis')

from databroker.assets.handlers_base import HandlerBase

# Set up isstools parsers
from isstools.xiaparser import xiaparser
from isstools.xasdata import xasdata
gen_parser = xasdata.XASdataGeneric(360000, db, db_analysis)
xia_parser = xiaparser.xiaparser()

# Import other stuff
import socket
from pathlib import Path
import os
import os.path as op
from subprocess import call
import json
import pickle
import pandas as pd
import numpy as np
import pwd
import grp

# Set up zeromq sockets
import zmq
context = zmq.Context()
machine_name = socket.gethostname()

# Create PULLER to receive information from workstations
receiver = context.socket(zmq.PULL)
receiver.connect("tcp://xf08id-srv2:5560")

# Create PUSHER to send information back to workstations
sender = context.socket(zmq.PUSH)
sender.connect("tcp://xf08id-srv2:5561")

#Setup beamline specifics:
beamline_gpfs_path = '/nsls2/xf08id/'
user_data_path = beamline_gpfs_path + 'User Data/'

# Set up logging.
import logging
import logging.handlers
logger = logging.getLogger('worker_srv')
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


class ScanProcessor():
    def __init__(self, gen_parser, xia_parser, db, beamline_gpfs_path, zmq_sender, username, *args, **kwargs):
        self.gen_parser = gen_parser
        self.xia_parser = xia_parser
        self.db = db
        self.md = {}
        self.root_path = Path(beamline_gpfs_path)
        self.user_data_path = Path(beamline_gpfs_path) / Path('User Data')
        self.xia_data_path = Path(beamline_gpfs_path) / Path('xia_files')
        self.sender = zmq_sender
        self.uid = pwd.getpwnam(username).pw_uid
        self.gid = grp.getgrnam(username).gr_gid

    def process(self, md, requester, interp_base='i0'):
        current_path = self.create_user_dirs(self.user_data_path,
                                             md['year'],
                                             md['cycle'],
                                             md['PROPOSAL'])
        try:
            current_filepath = Path(current_path) / Path(md['name'])
            current_filepath = ScanProcessor.get_new_filepath(str(current_filepath) + '.hdf5')
            current_uid = md['uid']
            self.gen_parser.load(current_uid)
        except:
            print("md['name'] not set")
            pass
        

        logger.info("Processing started for %s", md['uid'])
        if 'plan_name' in md:
            if md['plan_name'] == 'get_offsets':
                pass
            elif md['plan_name'] == 'execute_trajectory' or md['plan_name'] == 'execute_xia_trajectory':
                logger.info("Interpolation started for %s", md['uid'])
                
                if md['plan_name'] == 'execute_trajectory':
                    self.process_tscan(interp_base)
                elif md['plan_name'] == 'execute_xia_trajectory':
                    print(current_filepath)
                    self.process_tscanxia(md, current_filepath)
                    
                
                division = self.gen_parser.interp_df['i0'].values / self.gen_parser.interp_df['it'].values
                division[division < 0] = 1

                filename = self.gen_parser.export_trace_hdf5(current_filepath[:-5], '')
                os.chown(filename, self.uid, self.gid)

                filename = self.gen_parser.export_trace(current_filepath[:-5], '')
                os.chown(filename, self.uid, self.gid)

                logger.info('Interpolated file %s stored to ', filename)

                ret = create_ret('spectroscopy', current_uid, 'interpolate', self.gen_parser.interp_df,
                                 md, requester)
                self.sender.send(ret)
                logger.info('Interpolation of %s complete', filename)
                logger.info('Binning of %s started', filename)
                e0 = int(md['e0'])
                bin_df = self.gen_parser.bin(e0, e0 - 30, e0 + 30, 4, 0.2, 0.04)

                filename = self.gen_parser.data_manager.export_dat(current_filepath[:-5]+'.hdf5', e0)
                print(f"current_filepath: {current_filepath[:-5] + '.hdf5'}")
                os.chown(filename, self.uid, self.gid)
                logger.info('Binning of %s complete', filename)
                
                
                ret = create_ret('spectroscopy', current_uid, 'bin', bin_df, md, requester)
                self.sender.send(ret)
                logger.info("Processing comlplete for %s", md['uid'])

                
                #store_results_databroker(md,
                #                         parent_uid,
                #                         db_analysis,
                #                         'interpolated',
                #                         current_filepath[:-5] + '.hdf5',
                #                         root='')
            elif md['plan_name'] == 'relative_scan':
                pass

    def bin(self, md, requester, proc_info, filepath=''):
        logger.info("Binning started for %s", md['uid'])
        print('starting binning!', md['uid'])
        if filepath is not '':
            current_filepath = filepath
        else:
            current_path = self.create_user_dirs(self.user_data_path,
                                                 md['year'],
                                                 md['cycle'],
                                                 md['PROPOSAL'])
            current_filepath = str(Path(current_path) / Path(md['name'])) + '.txt'
        self.gen_parser.loadInterpFile(str(current_filepath))
        logger.info("Filepath %s", current_filepath)
        e0 = proc_info['e0']
        edge_start = proc_info['edge_start']
        edge_end = proc_info['edge_end']
        preedge_spacing = proc_info['preedge_spacing']
        xanes_spacing = proc_info['xanes_spacing']
        exafs_spacing = proc_info['exafs_spacing']
        bin_df = self.gen_parser.bin(e0, e0 + edge_start, e0 + edge_end, preedge_spacing, xanes_spacing, exafs_spacing)

        filename = self.gen_parser.data_manager.export_dat(f'{str(current_filepath)}', e0)
        
        os.chown(filename, self.uid, self.gid)
        ret = create_ret('spectroscopy', md['uid'], 'bin', bin_df, md, requester)
        logger.info('File %s binned', filename)
        self.sender.send(ret)
        logger.info("Binning complete for %s", md['uid'])
        print(os.getpid(), 'Done with the binning!') 

    def return_interp_data(self, md, requester, filepath=''):
        if filepath is not '':
            current_filepath = filepath
        else:
            current_path = self.create_user_dirs(self.user_data_path,
                                                 md['year'],
                                                 md['cycle'],
                                                 md['PROPOSAL'])
            current_filepath = str(Path(current_path) / Path(md['name'])) + '.txt'
        self.gen_parser.loadInterpFile(f'{str(current_filepath)}')
        ret = create_ret('spectroscopy', md['uid'], 'request_interpolated_data', self.gen_parser.interp_df, md, requester)
        self.sender.send(ret)

    def process_tscan(self, interp_base='i0'):
        print('Processing tscan')
        self.gen_parser.interpolate(key_base=interp_base)

    def process_tscanxia(self, md, current_filepath):
        # Parse xia
        print('Processing: xia scan')
        self.gen_parser.interpolate(key_base='xia_trigger')
        xia_filename = md['xia_filename']
        xia_filepath = 'smb://xf08id-nas1/xia_data/{}'.format(xia_filename)
        xia_destfilepath = Path(self.xia_data_path) / Path(xia_filename)
#        xia_destfilepath = '{}{}'.format(self.xia_data_path, xia_filename)
        smbclient = xiaparser.smbclient(xia_filepath, str(xia_destfilepath))
        try:
            smbclient.copy()
        except Exception as exc:
            if exc.args[1] == 'No such file or directory':
                print('*** File not found in the XIA! Check if the hard drive is full! ***')
            else:
                print(exc)
            print('Abort current scan processing!\nDone!')
            return

        interp_base = 'xia_trigger'
        self.gen_parser.interpolate(key_base=interp_base)
        xia_parser = self.xia_parser
        xia_parser.parse(xia_filename, self.xia_data_path)
        xia_parsed_filepath = current_filepath[0: current_filepath.rfind('/') + 1]
        xia_parser.export_files(dest_filepath=xia_parsed_filepath, all_in_one=True)

        try:
            if xia_parser.channelsCount():
                length = min(xia_parser.pixelsCount(0), len(self.gen_parser.interp_arrays['energy']))
                if xia_parser.pixelsCount(0) != len(self.gen_parser.interp_arrays['energy']):
                    len_xia = xia_parser.pixelsCount(0)
                    len_pb = len(self.gen_parser.interp_arrays['energy'])
                    raise Exception('XIA Pixels number ({}) != '
                                    'Pizzabox Trigger number ({})'.format(len_xia, len_pb))
            else:
                raise Exception("Could not find channels data in the XIA file")
        except Exception as exc:
            print('***', exc, '***')

        mcas = []
        if 'xia_rois' in md:
            xia_rois = md['xia_rois']
            if 'xia_max_energy' in md:
                xia_max_energy = md['xia_max_energy']
            else:
                xia_max_energy = 20

            for mca_number in range(1, xia_parser.channelsCount() + 1):
                if 'xia1_mca{}_roi0_high'.format(mca_number) in xia_rois:
                    rois_array = []
                    roi_numbers = [roi_number for roi_number in
                                   [roi.split('mca{}_roi'.format(mca_number))[1].split('_high')[0] for roi in
                                   xia_rois if len(roi.split('mca{}_roi'.format(mca_number))) > 1] if
                                   len(roi_number) <= 3]
                    for roi_number in roi_numbers:
                        rois_array.append(
                            [xia_rois['xia1_mca{}_roi{}_high'.format(mca_number, roi_number)],
                             xia_rois['xia1_mca{}_roi{}_low'.format(mca_number, roi_number)]])
                    mcas.append(xia_parser.parse_roi(range(0, length), mca_number, rois_array, xia_max_energy))
                else:
                    mcas.append(xia_parser.parse_roi(range(0, length), mca_number, [
                        [xia_rois['xia1_mca1_roi0_low'], xia_rois['xia1_mca1_roi0_high']]], xia_max_energy))

            for index_roi, roi in enumerate([[i for i in zip(*mcas)][ind] for ind, k in enumerate(roi_numbers)]):
                xia_sum = [sum(i) for i in zip(*roi)]
                if len(self.gen_parser.interp_arrays['energy']) > length:
                    xia_sum.extend([xia_sum[-1]] * (len(self.gen_parser.interp_arrays['energy']) - length))
                roi_label = ''
                #roi_label = getattr(self.parent_gui.widget_sdd_manager, 'edit_roi_name_{}'.format(roi_numbers[index_roi])).text()
                if not len(roi_label):
                    roi_label = 'XIA_ROI{}'.format(roi_numbers[index_roi])

                self.gen_parser.interp_df[roi_label] = np.array([xia_sum]).transpose()

                #self.gen_parser.interp_arrays[roi_label] = np.array(
                #    [self.gen_parser.interp_arrays['energy'][:, 0], xia_sum]).transpose()

                #self.figure.ax.plot(self.gen_parser.interp_arrays['energy'][:, 1], -(
                #    self.gen_parser.interp_arrays[roi_label][:, 1] / self.gen_parser.interp_arrays['i0'][:, 1]))

    def create_user_dirs(self, user_data_path, year, cycle, proposal):
        current_user_dir = Path(f"{year}.{cycle}.{proposal}")

        user_data_path = Path(user_data_path) / current_user_dir
        ScanProcessor.create_dir(user_data_path)

        log_path = user_data_path / Path('log')
        ScanProcessor.create_dir(log_path)

        snapshots_path = log_path / Path('snapshots')
        ScanProcessor.create_dir(snapshots_path)

        return user_data_path

    def get_new_filepath(filepath):
        if op.exists(Path(filepath)):
            if filepath[-5:] == '.hdf5':
                filepath = filepath[:-5]
            iterator = 2

            while True:
                new_filepath = f'{filepath}-{iterator}.hdf5'
                if not op.isfile(new_filepath):
                    return new_filepath
                iterator += 1
        return filepath

    def create_dir(path):
        if not op.exists(path):
            os.makedirs(path)
            call(['setfacl', '-m', 'g:iss-staff:rwx', path])
            call(['chown', '-R', 'xf08id:xf08id', path ])
            logger.info("Directory %s created succesfully", path)


def create_ret(scan_type, uid, process_type, data, metadata, requester):
    ret = {'type':scan_type,
           'uid': uid,
           'processing_ret':{
                             'type':process_type,
                             'data':data.to_msgpack(compress='zlib'),
                             'metadata': metadata
                            }
          }

    return (requester.encode() + pickle.dumps(ret))


if __name__ == "__main__":
    logger.info("Starting ScanProcessor....")
    processor = ScanProcessor(gen_parser, xia_parser, db, beamline_gpfs_path, sender, 'xf08id')
    
    logger.debug("Entering infinite loop...")
    while True:
        data = json.loads(receiver.recv().decode('utf-8'))
        md = db[data['uid']]['start']
    
        if data['type'] == 'spectroscopy':
            process_type = data['processing_info']['type']
    
            start_doc = md 
            if process_type == 'interpolate':
                processor.process(start_doc, requester=data['requester'], interp_base=data['processing_info']['interp_base'])
               
            elif process_type == 'bin':
                processor.bin(start_doc, requester=data['requester'], proc_info=data['processing_info'], filepath=data['processing_info']['filepath'])

            elif process_type == 'request_interpolated_data':
                processor.return_interp_data(start_doc, requester=data['requester'], filepath=data['processing_info']['filepath'])

#                interpolated_fn = '{}{}.{}.{}/{}.txt'.format(user_data_path,
#                                                        md['year'],
#                                                        md['cycle'],
#                                                        md['PROPOSAL'],
#                                                        md['name'])
#            
#                gen_parser.loadInterpFile(interpolated_fn)
#                bin_eq_data = pd.DataFrame(gen_parser.bin_equal(en_spacing=0.5)).to_json()
#            
#                process_info = data['processing_info']
#                bin_data = []
#                for info in process_info:
#                    bin_data.append(pd.DataFrame(gen_parser.bin(info['e0'],
#                                                   info['e0'] + info['edge_start'],
#                                                   info['e0'] + info['edge_end'],
#                                                   info['pre-edge'],
#                                                   info['xanes'],
#                                                   info['exafs'])).to_json())
#                print('Done: {}'.format(data['uid']))
#            
#                ret_msg = {'bin_eq_data': bin_eq_data, 'bin_data': bin_data}
#                sender.send((data['requester'] + json.dumps(ret_msg)).encode())
 
