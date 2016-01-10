# -*- coding: utf-8 -*-


class ModbusDriverFrontend(object):

    def load_frontend_config(self, config):
        self.frontend_config = config

        self.gearbox_ratio = (float(config["gearbox_input"]) /
                              float(config["gearbox_output"]))

        # Limits
        self.max_velocity = float(config["max_velocity"])
        self.max_acceleration = float(config["max_acceleration"])
        self.max_deceleration = float(config["max_deceleration"])

        self.min_torque_rise_time = float(config["min_torque_rise_time"])
        self.min_torque_fall_time = float(config["min_torque_fall_time"])

        # Actual values
        self.acceleration = float(config["acceleration"])
        self.deceleration = float(config["deceleration"])

        self.torque_rise_time = float(config["torque_rise_time"])
        self.torque_fall_time = float(config["torque_fall_time"])

    def init_startup_mode(self):
        if not hasattr(self, 'frontend_config'):
            raise ValueError('Config not found')

    def enable_drive(self):
        self['jog'] = 0
        self['torque_ref'] = 0
        self['velocity_ref'] = 0
        self['command:enable'] = True

    def disable_drive(self):
        self['jog'] = 0
        self['torque_ref'] = 0
        self['velocity_ref'] = 0
        self['command:enable'] = False

    def reset_drive(self):
        self['command:reset'] = False
        self['command:reset'] = True

    def clear_errors(self):
        self['command:clear_errors'] = False
        self['command:clear_errors'] = True

    def cancel(self):
        self['command:cancel'] = False
        self['command:cancel'] = True

    def set_mode(self, mode):
        if 'torque' == mode:
            self['torque_ref'] = 0
            self['velocity_ref'] = 0
            self['command:control_mode'] = 1
        elif 'velocity' == mode:
            self['torque_ref'] = 0
            self['velocity_ref'] = 0
            self['command:control_mode'] = 2
        elif 'position' == mode:
            self['torque_ref'] = 0
            self['velocity_ref'] = 0
            self['command:control_mode'] = 3
        elif 'enhanced_torque' == mode:
            self['torque_ref'] = 0
            self['velocity_ref'] = 0
            self['command:control_mode'] = 4
        else:
            raise ValueError('Unrecognized mode: {}'.format(mode))

        return mode

    def set_velocity(self, v):
        self['velocity_ref'] = v if not self.invert else -v

        return v

    def set_torque_time(self, rt=None, ft=None):
        if rt is None:
            rt, ft = self.torque_rise_time, self.torque_fall_time
        elif ft is None:
            ft = rt

        if rt < self.min_torque_rise_time:
            raise ValueError('Torque rise time is too small: {} vs {}'.format(
                rt, self.min_torque_rise_time))
        elif ft < self.min_torque_fall_time:
            raise ValueError('Torque fall time is too small: {} vs {}'.format(
                ft, self.min_torque_fall_time))

        self['torque_rise_time'] = rt
        self['torque_fall_time'] = ft

        return rt, ft

    def set_acceleration(self, acc=None, decc=None):
        if acc is None:
            acc, dec = self.acceleration, self.deceleration
        elif dec is None:
            dec = acc

        if acc > self.max_acceleration:
            raise ValueError('Acceleration is too big: {} vs {}'.format(
                acc, self.max_acceleration))
        elif dec > self.max_deceleration:
            raise ValueError('Deceleration is too big: {} vs {}'.format(
                dec, self.max_deceleration))

        self['acceleration'] = dec
        self['deceleration'] = acc

        return acc, dec
