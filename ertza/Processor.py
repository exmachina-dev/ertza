# -*- coding: utf-8 -*-


import importlib
import inspect
import logging

from threading import Event
from queue import PriorityQueue

from commands.AbstractCommands import BufferedCommand
from commands.AbstractCommands import SyncedCommand


class PrioritizedSyncQueue(PriorityQueue):
    pass


class Processor(object):
    def __init__(self, base_module, abstract_class, machine):
        self.base_module = base_module
        self.abstract_class = abstract_class
        self.machine = machine

        self.commands = {}

        try:
            module = __import__(base_module, globals=globals(), locals=locals())
        except ImportError:
            module = importlib.import_module("ertza.%s" % base_module)

        self.load_classes_in_class(module)

    def load_classes_in_module(self, module):
        for module_name, obj in inspect.getmemebesr(module):
            if issubclass(obj, self.abstract_class):
                self.commands[module_name] = obj(self.machine)

    def available_commands(self):
        for command in self.commands:
            yield command

    def is_buffered(self, command):
        if isinstance(command, BufferedCommand):
            return True

        return False

    def is_synced(self, command):
        if isinstance(command, SyncedCommand):
            return True

        return False

    def synchronize(self, command):
        alias = self._check_in_commands(command)
        if alias:
            try:
                self.commands[alias].on_sync(command)
            except Exception as e:
                logging.error("Error while executing %s: %s", alias, e)
            return command

    def execute(self, command):
        alias = self._check_in_commands(command)
        if alias:
            try:
                if self.commands[alias].synced:
                    self.commands[alias].readyEvent = Event()

                self.commands[alias].execute(command)

                if self.commands[alias].synced:
                    self.commands[alias].readyEvent.wait()
            except Exception as e:
                logging.error("Error while executing %s: %s", alias, e)
            return command

    def _check_in_commands(self, command):
        alias = command.alias
        if alias not in self.commands:
            logging.error("Alias not found in commands.")
            return None

        return alias