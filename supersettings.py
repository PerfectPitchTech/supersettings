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
from six.moves import configparser
from collections import OrderedDict

import os
import logging
import re
import traceback

log = logging.getLogger(__name__)

SECTION_REGEX = re.compile('%\((\w+):(\w+)\)s')


def resolve_string(str, context=None):
    if context:
        try:
            str = str.format(**context)
        except KeyError:
            raise
        if str.startswith('$') or str.startswith('%'):
            name = str[1:]
            return context[name]
    return str


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
    if hasattr(configparser, 'ExtendedInterpolation'):
        _DEFAULT_INTERPOLATION = configparser.ExtendedInterpolation()

    def __init__(self, file_name, default_file=None, auto_read=True, *args, **kwargs):
        self.file_name = file_name
        self.default_file = default_file
        super(configparser.ConfigParser, self).__init__(*args, **kwargs)
        self.config_files = []
        if auto_read:
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
        home_config = None
        if "HOME" in os.environ:
            try:
                home_config = os.path.join(os.environ.get('HOME'), '.{}'.format(self.file_name))
            except AttributeError:
                log.info('Unable to load home configs.')

        config_files = [default_config, etc_config, home_config]
        for cf in config_files:
            self.add_config_file(cf)

    def get(self, section, option, raw=False, vars=None, fallback=None, context=None):
        v = super(MultiFileConfigParser, self).get(section, option, raw=raw, vars=vars, fallback=fallback)
        if context:
            v = resolve_string(v, context)
        return v

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

    def getsettings(self, section, context=None):
        return OrderedDict(
            self.items(
                section,
                context=context,
                key_formatter=lambda k, c: resolve_string(str(k).upper()))
        )

    def items(self, section, raw=False, vars=None, context=None, key_formatter=None, value_formatter=None):
        key_formatter = key_formatter or resolve_string
        value_formatter = value_formatter or resolve_string
        items = super(MultiFileConfigParser, self).items(section, raw, vars)
        return [(key_formatter(k, context), value_formatter(v, context)) for k, v in items]

    def getenv(self, section, option, key=None, type=str, context=None):
        """
        Try and get the option out of os.enviorn and cast it, otherwise return the default (casted)
        :param section: settings section name
        :param option: the name of the option
        :param key: The name of the os.enviorn key.  Defaults to option.
        :param type: the type to cast it to
        :return: parsed value
        """
        if key is None:
            key = option
        value = os.environ.get(key, None)
        try:
            return type(value)
        except TypeError:
            pass
        return type(self.get(section, option, context=context))
