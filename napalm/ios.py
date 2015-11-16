# Copyright 2015 Spotify AB. All rights reserved.
#
# The contents of this file are licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

from netmiko import ConnectHandler, FileTransfer
from base import NetworkDriver
import random
import string


from exceptions import MergeConfigException, ReplaceConfigException, SessionLockedException
from datetime import datetime
import time
from utils import string_parsers


class IOSDriver(NetworkDriver):

    def __init__(self, hostname, username, password, secret='', port=22, device_type='cisco_ios',
                 verbose=False, use_keys=False, key_file=None, global_delay_factor=None,
                 candidate_config='candidate_config.txt', dest_file_system='flash:')
        self.ssh_session = None
        self.hostname = hostname
        self.username = username
        self.password = password
        self.secret = secret
        self.port = port
        self.device_type = device_type
        self.verbose = verbose
        self.use_keys = use_keys
        self.key_file = key_file
        self.global_delay_factor = global_delay_factor
        self.candidate_config = candidate_config
        self.dest_file_system = dest_file_system

    def open(self):
        self.ssh_session = ConnectHandler(ip=self.hostname, username=self.username,
                                          password=self.password, secret=self.secret,
                                          port=self.port, device_type=self.device_type,
                                          verbose=self.verbose, use_keys=self.use_keys,
                                          key_file=self.key_file,
                                          global_delay_factor=self.global_delay_factor)

    def close(self):
        self.disconnect()
        self.ssh_session = None

    def load_replace_candidate(self, filename=None, config=None):
        '''
        Only supports transfer file file_name not via config string
        '''
        if filename is None:
            raise NotImplementedError
        with FileTransfer(self.ssh_session, source_file=filename, dest_file=self.candidate_config,
                          file_system=self.dest_file_system) as scp_transfer:
            scp_transfer.transfer_file()

    def load_merge_candidate(self, filename=None, config=None):
        raise NotImplementedError

    def compare_config(self):
        '''
        show archive config differences flash:test_config.txt system:running-config
        '''

        if self.ssh_session is None:
            return ''
        else:
            cmd = 'show archive config differences {}:{} system:running-config' \
                .format(self.dest_file_system, self.candidate_config)
            result = self.ssh_session.send_command(cmd)
            return result.strip()

    def commit_config(self):
        if self.ssh_session is None:
            return ''
        cmd = 'configure replace {}:{} force'.format(self.dest_file_system, self.candidate_config)
        result = net_connect.send_command(cmd)
        result += net_connect.send_command('write memory')

    def discard_config(self):
        if self.config_session is not None:
            commands = list()
            commands.append('configure session {}'.format(self.config_session))
            commands.append('abort')
            self.device.run_commands(commands)
            self.config_session = None

    def rollback(self):
        commands = list()
        commands.append('configure replace flash:rollback-0')
        commands.append('write memory')
        self.device.run_commands(commands)

    def get_facts(self):
        commands = list()
        commands.append('show version')
        commands.append('show hostname')
        commands.append('show interfaces status')

        result = self.device.run_commands(commands)

        version = result[0]
        hostname = result[1]
        interfaces_dict = result[2]['interfaceStatuses']

        uptime = time.time() - version['bootupTimestamp']

        interfaces = [i for i in interfaces_dict.keys() if '.' not in i]
        interfaces = string_parsers.sorted_nicely(interfaces)

        return {
            'hostname': hostname['hostname'],
            'fqdn': hostname['fqdn'],
            'vendor': u'Arista',
            'model': version['modelName'],
            'serial_number': version['serialNumber'],
            'os_version': version['internalVersion'],
            'uptime': int(uptime),
            'interface_list': interfaces,
        }

    def get_interfaces(self):
        commands = list()
        commands.append('show interfaces')
        output = self.device.run_commands(commands)[0]

        interfaces = dict()

        for interface, values in output['interfaces'].iteritems():
            interfaces[interface] = dict()

            if values['lineProtocolStatus'] == 'up':
                interfaces[interface]['is_up'] = True
                interfaces[interface]['is_enabled'] = True
            else:
                interfaces[interface]['is_up'] = False
                if values['interfaceStatus'] == 'disabled':
                    interfaces[interface]['is_enabled'] = False
                else:
                    interfaces[interface]['is_enabled'] = True

            interfaces[interface]['description'] = values['description']

            interfaces[interface]['last_flapped'] = values.pop('lastStatusChangeTimestamp', None)

            interfaces[interface]['speed'] = values['bandwidth']
            interfaces[interface]['mac_address'] = values.pop('physicalAddress', None)

        return interfaces

    def get_lldp_neighbors(self):
        commands = list()
        commands.append('show lldp neighbors')
        output = self.device.run_commands(commands)[0]['lldpNeighbors']

        lldp = dict()

        for n in output:
            if n['port'] not in lldp.keys():
                lldp[n['port']] = list()

            lldp[n['port']].append(
                {
                    'hostname': n['neighborDevice'],
                    'port': n['neighborPort'],
                }
            )

        return lldp

