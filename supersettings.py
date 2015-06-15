"""
Multi-file config parser for any library.
Not usually to be used alone, usually you ready from the parser into a settings file.

Changes can be made by creating / updating a ~/.{{file_name}} in your home directory or an /etc/.{{file_name}} file for
system wide settings.

Imports are in the following order:
1. Home Directory always overrides any other settings
2. /etc/default/{{file_name}} overrides defaults
3. Defaults are used last

For help with config files please see:
https://docs.python.org/2/library/configparser.html

"""
import configparser
from collections import OrderedDict

import os
import logging
import re
import traceback


log = logging.getLogger(__name__)

SECTION_REGEX = re.compile('%\((\w+):(\w+)\)s')

__author__ = 'gdoermann'


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self

    def __deepcopy__(self, memo):
        dcopy = type(self)(**self)
        memo[id(self)] = dcopy
        return dcopy


class MultiFileConfigParser(configparser.ConfigParser):
    """
    Pulls in multiple config files and merges them into one configuration.
    Resolves variables with a context and can replace objects:
        $<variable> will resolve to a python object out of the context.
        {variable} will be formatted as a string out of the context.
    """
    file_name = None
    _DEFAULT_INTERPOLATION = configparser.ExtendedInterpolation()

    def __init__(self, file_name, default_file=None, *args, **kwargs):
        self.file_name = file_name
        self.default_file = default_file
        super(configparser.ConfigParser, self).__init__(*args, **kwargs)
        self.config_files = []
        self.read_configs()

    def add_config_file(self, path, required=False):
        if path:
            if os.path.exists(path):
                self.config_files.append(path)
                try:
                    self.read(path)
                except:
                    log.error('Failed to load file {}: {}'.format(path, traceback.format_exc()))
                    raise
            else:
                if not required:
                    log.info('Configuration path does not exist, skipping: {}'.format(path))
                else:
                    raise ValueError('Required configuration file does not exist: {}'.format(path))

    def read_configs(self):
        default_config = self.default_file
        etc_config = '/etc/default/{}'.format(self.file_name)
        try:
            home_config = os.path.join(os.environ.get('HOME'), '.{}'.format(self.file_name))
        except AttributeError:
            log.info('Unable to load home configs.')
            home_config = None
        config_files = [default_config, etc_config, home_config]
        for cf in config_files:
            self.add_config_file(cf)

    def gettuple(self, section, option, delimiter=','):
        val = self.get(section, option)
        return tuple([v.strip() for v in val.split(delimiter) if v])

    def getlist(self, section, option, delimiter=','):
        val = self.get(section, option)
        return list([v.strip() for v in val.split(delimiter) if v])

    def getdict(self, section):
        return OrderedDict(self.items(section))

    def getvalues(self, section):
        return self.getdict(section).values()

    def getkeys(self, section):
        return self.getdict(section).keys()

    def getsettings(self, section):
        return OrderedDict([(str(k).upper(), v) for k, v in self.items(section)])
