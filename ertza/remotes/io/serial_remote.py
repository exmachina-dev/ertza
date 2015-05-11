# -*- coding: utf-8 -*-

from collections import namedtuple

from ...errors import SerialError

import serial, bitstring

class SerialControlLink(serial.Serial):
    product_keys = ('product_id', 'device_id', None, None)
    word_keys = namedtuple('WordKeys', ['ticks', 'turns', 'speed'])(0, 1, 2)
    command_keys = namedtuple('Command', ['ticks', 'turns', 'speed'])(
            b'K', b'T', b'S')

    word_length = 4 # bytes
    command_length = 2 # bytes
    word_number = 3

    line_length = 20 # bytes

    daemon_refresh = 0.4

    remote_mode = 'continuous'
    min_speed = 0
    max_speed = 0

    dead_zone = 20
    init_range = 800

    def __init__(self, port=None, baudrate=57600):
        super(SerialControlLink, self).__init__(port=port, baudrate=baudrate)
        self.bytesize = serial.EIGHTBITS
        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE
        self.timeout = 0.05
        self.xonxoff = False

        self.data_buffer = b''

        self.product_infos = {}

        self.last_ticks = 0
        self.last_turns = 0
        self.last_speed = 0
        self.last_mapped_speed = 0

        self.lost_data = 0
        self.max_lost_data = 10

    def _send_command(self, cmd, data=None):
        if not type(cmd) in (str, bytes):
            raise TypeError('Cmd must be a string or a byte')
        if len(cmd) != 1:
            raise ValueError('Cmd must be a string of length 1.')

        if type(cmd) is str:
            cmd.encode()

        if data:
            if type(data) is tuple and len(data) <= 4:
                d = bitstring.pack('>BBBB', *data)
            elif type(data) is int:
                d = bitstring.pack('>l', data)
            elif type(data) is float:
                d = bitstring.pack('>f', data)
            bits = bitstring.pack('bits', d)
        else:
            bits = bitstring.Bits()
        final_bytes = bitstring.pack(
                'uint:8, bits, uint:8',
                ord(cmd), bits, ord('\n'))
        return self.write(final_bytes.tobytes())

    def _serial_daemon(self):
        if self.remote_mode == 'continuous':
            while not self.daemon_event.is_set():
                print(self.safe_get())
                self.daemon_event.wait(self.daemon_refresh)
        elif self.remote_mode == 'on_command':
            while not self.daemon_event.is_set():
                self.request_speed()
                self.request_ticks()
                self.request_turns()
                self.daemon_event.wait(self.daemon_refresh)

    def safe_get(self):
        if self.get_last_data():
            self.lost_data = 0
            self.get_ticks()
            self.get_turns()
            self.map_to_speed(self.last_ticks)
            return self.last_ticks, self.last_turns, self.last_mapped_speed
        else:
            self.lost_data += 1
            print('Data skipped.')
            if self.lost_data >= self.max_lost_data:
                raise SerialError('Too much failed data get.')
            return self.last_ticks, self.last_turns, self.last_mapped_speed

    def run(self):
        if self.remote_mode == 'continuous':
            print(self.get_last_data())
            print(self.get_ticks())
            print(self.get_turns())
            print(self.map_to_speed(self.last_ticks))
        elif self.remote_mode == 'on_command':
            self.request_speed()
            self.request_ticks()
            self.request_turns()

    def get_product_infos(self):
        self._send_command("R")
        r = self.readline()
        d = bitstring.Bits(bytes=r)
        if r[0] == ord('R'):
            d = bitstring.Bits(bytes=r[1:]).unpack('>BBBBB')
            for k, v in zip(self.product_keys, d):
                self.product_infos[k] = v
            return self.product_infos
        raise SerialError("Unexpected serial command")

    def get_speed(self):
        speed_c = self._get_data(self.word_keys.speed, 'float')
        self.last_speed = speed_c
        return self.last_speed

    def get_ticks(self):
        ticks_c = self._get_data(self.word_keys.ticks, 'long')
        self.last_ticks = ticks_c
        return self.last_ticks

    def get_turns(self):
        turns_c = self._get_data(self.word_keys.turns, 'float')
        self.last_turns = turns_c
        return self.last_turns

    def request_speed(self):
        raise NotImplementedError

    def request_ticks(self):
        raise NotImplementedError

    def request_turns(self):
        raise NotImplementedError

    def read_latest_data_frame(self):
        temp_data = self.read(40)
        pos = temp_data.rfind(b'\r\nR')
        if pos >= 0:
            line, after = temp_data[:pos+2], temp_data[pos+2:]
            self.flushInput()
            return line[-self.line_length:]
        return bytes()

    def get_last_data(self):
        data = self.read_latest_data_frame()
        if len(data) == self.line_length:
            pos = data.find(b'RK')
            self.last_data = data[pos:]
            return True
        else:
            print(data, len(data))
            self.last_data = None
        return False

    def _get_data(self, word, data_type):
        if self.last_data in (False, None):
            return False

        cmd = b'R' + self.command_keys[word]
        next_cmd = b'R' + self.command_keys[word+1]
        pos_start = self.last_data.find(cmd)
        pos_end = self.last_data.find(next_cmd)
        if -1 in (pos_start, pos_end):
            return False
        data = self.last_data[pos_start+2:pos_end]
        if len(data) != 4:
            return False

        if data_type == 'long':
            data_format = '<l'
        elif data_type == 'float':
            data_format = '<f'
        else:
            return False

        try:
            bits = bitstring.Bits(bytes=data).unpack(data_format)[0]
        except bitstring.ReadError:
            return False
        return bits

    def map_to_speed(self, ticks):
        try:
            if ticks < self.min_ticks:
                self.min_ticks = ticks
            if ticks > self.max_ticks:
                self.max_ticks = ticks
        except AttributeError:
            self.min_ticks = ticks
            self.max_ticks = ticks + self.init_range

        abs_ticks = (self.min_ticks - ticks)
        abs_max_ticks = (self.min_ticks - self.max_ticks)

        abs_ticks += self.dead_zone
        abs_max_ticks += self.dead_zone
        if abs_ticks <= 0:
            abs_ticks
        rate_ticks = abs_ticks / abs_max_ticks

        mapped_speed = self.max_speed * rate_ticks
        if mapped_speed <= self.min_speed:
            mapped_speed = self.min_speed
        self.last_mapped_speed = mapped_speed
        return mapped_speed


if __name__ == '__main__':
    test = input('Start serial test [y/N] ? ')
    if test and test == 'y':
        default_device = '/dev/ttyUSB0'
        dev = input('Serial device [%s]: ' % default_device)
        if not dev:
            dev = default_device
        from threading import Event
        SerialControlLink.max_speed = 72.5
        s = SerialControlLink(dev)
        s.daemon_event = Event()
    else:
        s = SerialControlLink()
