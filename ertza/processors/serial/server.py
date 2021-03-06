# -*- coding: utf-8 -*-

import logging
import time
import serial as sr
from threading import Thread

from .message import SerialMessage, SerialCommandString

logging = logging.getLogger('ertza.processors.serial.server')


class SerialServer(sr.Serial):
    identifier = 'Serial'

    def __init__(self, outlet, config):
        self._outlet_coro = outlet

        dev = config.get('listen_device')
        if dev == 'None':
            dev = None
        baudrate = int(config.get('baudrate', fallback=57600))

        logging.debug('Initializing serial server on {} at {}'
                      . format(dev, baudrate))
        super().__init__(port=None, baudrate=baudrate)

        self.port = dev

        self.bytesize = sr.EIGHTBITS
        self.parity = sr.PARITY_NONE
        self.stopbits = sr.STOPBITS_ONE
        self.timeout = 1
        self.xonxoff = False
        self.rtscts = False

        self.rts = True
        self.dtr = True

        self.break_condition = False

        self.data_buffer = b''

        self.running = False
        self._last_read_time = time.time()

    def run(self):
        try:
            self.open()
        except sr.SerialException as e:
            self.running = False
            logging.error(e)

        while self.running:
            try:
                # read all that is there or wait for one byte
                data = self.read(self.inWaiting() or 1)
                if time.time() > (self._last_read_time + self.timeout):     # Empty buffer if data is older than timeout
                    self.data_buffer = b''

                self._last_read_time = time.time()
                self.data_buffer += (data)
                self.find_serial_packets()

            except sr.SerialException as e:
                logging.error(str(e))
            except Exception as e:
                logging.error(str(e))

    def start(self):
        self.running = True
        self._outlet = self._outlet_coro(self.identifier)

        self._t = Thread(target=self.run)
        self._t.daemon = True
        self._t.start()

        m = SerialMessage()
        m.cmd_bytes['data'] = 'alive'
        self.send_message(m)

    def send_message(self, message):
        if not self.running:
            logging.error('Serial port is not opened. Aborting.')
            return

        if message.msg_type is not 'log':
            logging.debug("Sending: %s %s" % (message, message.tobytes))
        self.write(message.tobytes)
        self.flush()

    def close(self):
        logging.debug("Closing serial server")
        self.running = False
        self._t.join()

    def exit(self):
        self.close()

    def find_serial_packets(self):
        pos = self.data_buffer.find(SerialCommandString.CmdEnd)
        if pos >= 0:
            packet, self.data_buffer = self.data_buffer[:pos+2], \
                self.data_buffer[pos+2:]
            m = SerialMessage(cmd_bytes=packet)
            l = m.length
            if len(m) != l:
                reply = SerialMessage(cmd_bytes=packet)
                reply.cmd_bytes['data'] = reply.cmd_bytes['data'].split(b':')[0] + b'.error'
                e = 'Invalid length specified in {}: ' \
                    '{} != {}'.format(m, l, len(m))
                reply.cmd_bytes += e
                self.send_message(reply)
                raise ValueError(e)
            self._outlet.send(m)
            self.find_serial_packets()
