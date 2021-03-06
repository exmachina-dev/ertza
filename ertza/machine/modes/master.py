# -*- coding: utf-8 -*-

import time
import logging

from .abstract_machinemode import ContinueException, MachineModeException
from .standalone import StandaloneMachineMode

logging = logging.getLogger('ertza.machine.modes.master')


class SlavesConfig(object):
    def __init__(self, config, slave_machines):
        self._cf = config
        self.update_slave_configs(slave_machines)

    def update_slave_configs(self, slave_machines):
        self._slaves = [sm.slave for sm in slave_machines.values()]

    def __getitem__(self, key):
        try:
            sn, opt = key.split(':', maxsplit=1)
            opt = opt.replace(':', '.')
            c = self._cf['slave_{}'.format(sn)]

            try:
                m = c['{}_mode'.format(opt)]
            except KeyError:
                m = 'forward'

            try:
                v = float(c['{}_value'.format(opt)])
            except KeyError:
                v = None

            return m, v
        except KeyError:
            raise KeyError('No config found for {}'.format(key.split(':', maxsplit=1)[0]))

    def keys(self):
        return [s.serialnumber for s in self._slaves]


class MasterMachineMode(StandaloneMachineMode):
    _param = StandaloneMachineMode._param

    StandaloneMachineMode.MachineMap.update({
        'slaves':   _param(str, 'r'),
    })

    DefaultForwardKeys = (
        'command:enable',
        'command:cancel',
        'command:clear_errors',
        'command:reset',
    )

    ForwardKeys = {
        'torque': (
            'torque_ref',
            'torque_rise_time',
            'torque_fall_time',
        ),
        'enhanced_torque': (
            'torque_ref',
            'torque_rise_time',
            'torque_fall_time',
            'velocity_ref',
        ),
        'velocity': (
            'velocity_ref',
            'acceleration',
            'deceleration',
        ),
        'position': (
            'command:move_mode',
            'command:go',
            'command:set_home',
            'command:go_home',
            'velocity_ref',
            'position_ref',
            'acceleration',
            'deceleration',
        ),
    }

    ValueGuard = {}

    def __init__(self, machine):
        super().__init__(machine)

        self.guard_interval = 0.03

        self._slv_config = SlavesConfig(self._machine.config, self._machine.slave_machines)

    def _send_to_slave(self, slave, mode=None, key='', value=None):
        if not mode:
            return
        if key in self.ForwardKeys[mode]:
            value = self.get_value_for_slave(slave, key, value) or value
            slave.set_to_remote(key, value)
        if key in self.DefaultForwardKeys:
            slave.set_to_remote(key, value)

    def get_value_for_slave(self, slave_machine, key, value=None):
        sn = slave_machine.slave.serialnumber

        if sn not in self._slv_config.keys():
            logging.warn('No config registered for slave {!s}'.format(slave_machine))
            return

        if key is None:
            raise MachineModeException('Key cannot be None')

        try:
            vl_mode, vl_value = self._slv_config['{}:{}'.format(sn, key)]
        except KeyError as e:
            vl_mode, vl_value = 'forward', None
            logging.debug('{!s}'.format(e))

        if vl_mode not in ('forward', 'multiply', 'divide', 'add', 'substract', 'default',):
            raise MachineModeException('Unrecognized mode {0} for {1}'.format(vl_mode, key))

        if vl_mode in ('multiply', 'divide', 'add', 'substract', 'default',) and vl_value is None:
            raise MachineModeException('No value configured for '
                                       '{0} in {1!s}'.format(key, slave_machine))
        if vl_mode == 'default':
            return vl_value

        if not value:
            if key in self.StaticKeys:
                value = self._last_values.get(key, self._machine[key])
            else:
                try:
                    value = self.get_guarded_value(key)
                except ContinueException:
                    raise MachineModeException('No value returned for '
                                               '{0.slave.serialnumber} '
                                               '({1} asked)'.format(slave_machine, key))

        nvalue = None
        if vl_mode == 'forward':
            nvalue = value
        elif vl_mode == 'multiply':
            nvalue = vl_value * value
        elif vl_mode == 'divide':
            nvalue = vl_value / value
        elif vl_mode == 'add':
            nvalue = vl_value + value if value >= 0 else vl_value - value
        elif vl_mode == 'substract':
            nvalue = vl_value - value if value >= 0 else vl_value + value

        if nvalue is not None and value != nvalue:
            logging.debug('Modified value for key {}: '
                          '{} to {} ({} {})'
                          .format(key, value,
                                  nvalue, vl_mode, vl_value))
        return nvalue

    def get_guarded_value(self, key):
        gvalue, gtime = self.ValueGuard.get(key, (None, None,))
        if gtime is not None:
            if time.time() - gtime > self.guard_interval:
                nvalue = self._machine[key]
                ntime = time.time()
                self.ValueGuard[key] = (nvalue, ntime)
                return nvalue
            else:
                return gvalue
        else:
            nvalue = self._machine[key]
            ntime = time.time()
            self.ValueGuard[key] = (nvalue, ntime)
            return nvalue
