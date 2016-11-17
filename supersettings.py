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
import logging
import os
import re
import traceback
from collections import OrderedDict
import six

from backports import configparser
from backports.configparser import NoOptionError, InterpolationSyntaxError, InterpolationDepthError, \
    MAX_INTERPOLATION_DEPTH, NoSectionError, InterpolationMissingOptionError, from_none, _UNSET

log = logging.getLogger(__name__)

SECTION_REGEX = re.compile('%\((\w+):(\w+)\)s')


class SuperInterpolator(configparser.ExtendedInterpolation):
    _KEYCRE = re.compile(r"\$\{([^}]+)\}|\$\(([^)]+)\)")

    def before_get(self, parser, section, option, value, defaults, context=None):
        L = []
        self._interpolate_some(parser, option, L, value, section, defaults, 1, context=context)
        if all((isinstance(x, six.string_types) for x in L)):
            return ''.join(L)
        return L[0]

    def _interpolate_some(self, parser, option, accum, rest, section, map, depth, context=None):
        if not isinstance(rest, six.string_types):
            return
        rawval = parser.get(section, option, raw=True, fallback=rest)
        if depth > MAX_INTERPOLATION_DEPTH:
            raise InterpolationDepthError(option, section, rawval)
        while rest:
            p = rest.find("$")
            if p < 0:
                accum.append(rest)
                return
            if p > 0:
                accum.append(rest[:p])
                rest = rest[p:]
            # p is no longer used
            c = rest[1:2]
            c_groups = ["{", "("]
            if c == "$":
                accum.append("$")
                rest = rest[2:]
            elif c in c_groups:
                m = self._KEYCRE.match(rest)
                if m is None:
                    raise InterpolationSyntaxError(option, section,
                                                   "bad interpolation variable reference %r" % rest)
                group = c_groups.index(c) + 1

                path = m.group(group).split(':')
                rest = rest[m.end():]
                sect = section
                opt = option
                v = ""
                try:
                    if group == 1:
                        if len(path) == 1:
                            opt = parser.optionxform(path[0])
                            v = map[opt]
                        elif len(path) == 2:
                            sect = path[0]
                            opt = parser.optionxform(path[1])
                            v = parser.get(sect, opt, raw=True)
                        else:
                            raise configparser.InterpolationSyntaxError(
                                option, section,
                                "More than one ':' found: %r" % (rest,))
                    elif group == 2:
                        if not context:
                            raise configparser.InterpolationError(option, section, "Trying to interpolate from "
                                                                                   "context with no context!")
                        if len(path) == 1:
                            v = context[path[0]]
                        else:
                            raise configparser.InterpolationSyntaxError(
                                option, section,
                                "More than one ':' found: %r" % (rest,))
                except (KeyError, NoSectionError, NoOptionError):
                    raise from_none(InterpolationMissingOptionError(
                        option, section, rawval, ":".join(path)))

                if v and "$" in v:
                    self._interpolate_some(parser, opt, accum, v, sect,
                                           dict(parser.items(sect, raw=True)),
                                           depth + 1, context=context)
                elif v:
                    accum.append(v)
            else:
                raise InterpolationSyntaxError(
                    option, section,
                    "'$' must be followed by '$' or '{' or '(', "
                    "found: %r" % (rest,))

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
    _DEFAULT_INTERPOLATION = SuperInterpolator()

    def __init__(self, file_name, default_file=None, auto_read=True, *args, **kwargs):
        self.file_name = file_name
        self.default_file = default_file
        super(MultiFileConfigParser, self).__init__(*args, **kwargs)
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

    def get(self, section, option, **kwargs):
        raw = kwargs.get('raw', False)
        vars = kwargs.get('vars', None)
        fallback = kwargs.get('fallback', _UNSET)
        context = kwargs.get('context', None)
        try:
            d = self._unify_values(section, vars)
        except NoSectionError:
            if fallback is _UNSET:
                raise
            else:
                return fallback
        option = self.optionxform(option)
        try:
            value = d[option]
        except KeyError:
            if fallback is _UNSET:
                raise NoOptionError(option, section)
            else:
                return fallback

        if raw or value is None:
            return value
        else:
            return self._interpolation.before_get(self, section, option, value, d, context=context)

    def gettuple(self, section, option, delimiter=',', context=None):
        val = self.get(section, option, context=context)
        return tuple([v.strip() for v in val.split(delimiter) if v])

    def getlist(self, section, option, delimiter=',', context=None):
        val = self.get(section, option, context=context)
        return list([v.strip() for v in val.split(delimiter) if v])

    def getdict(self, section, context=None):
        return OrderedDict(self.items(section, context=context))

    def getvalues(self, section, context=None):
        return self.getdict(section, context=context).values()

    def getkeys(self, section, context=None):
        return self.getdict(section, context=context).keys()

    def getsettings(self, section, raw=False, vars=None, context=None):
        return OrderedDict(((str(k).upper(), v) for k, v in self.items(section, raw=raw, vars=vars, context=context)))

    def items(self, section=_UNSET, raw=False, vars=None, context=None):
        if section is _UNSET:
            return super(MultiFileConfigParser, self).items()
        d = self._defaults.copy()
        try:
            d.update(self._sections[section])
        except KeyError:
            if section != self.default_section:
                raise NoSectionError(section)
        # Update with the entry specific variables
        if vars:
            for key, value in vars.items():
                d[self.optionxform(key)] = value
        value_getter = lambda option: self._interpolation.before_get(self,
            section, option, d[option], d, context=context)
        if raw:
            value_getter = lambda option: d[option]
        return ((option, value_getter(option)) for option in d.keys())


    def getenv(self, section, option, key=None, type=str):
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
        return type(self.get(section, option))
