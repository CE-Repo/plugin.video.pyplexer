# -*- coding: utf-8 -*-

import re
import sys
import traceback

import xbmc  # pylint: disable=import-error

from core.constants import CONFIG
from core.settings import AddonSettings

#: Shared settings instance. Nearly every module creates a module level
#: ``Logger`` at import time; giving each one its own ``AddonSettings`` meant
#: constructing an ``xbmcaddon.Addon()`` a dozen or more times per invocation.
_SETTINGS = None


def _shared_settings():
    global _SETTINGS  # pylint: disable=global-statement
    if _SETTINGS is None:
        _SETTINGS = AddonSettings()
    return _SETTINGS


class Logger:
    LOG_NOTICE = -1
    LOG_DEBUG = 0
    LOG_DEBUGPLUS = 1
    LOG_ERROR = 9
    LOG_DISABLED = 2  # value of the 'debug' setting that silences logging
    DEBUG_MAP = {
        LOG_NOTICE: 'notice',
        LOG_DEBUG: 'debug',
        LOG_DEBUGPLUS: 'debug+',
        LOG_ERROR: 'error'
    }
    KODI_LEVELS = {
        LOG_ERROR: xbmc.LOGERROR,
        LOG_NOTICE: xbmc.LOGINFO,
    }

    token_regex = re.compile(r'-Token=[a-zA-Z0-9|\-_]+([\s&|\'"])+')
    token2_regex = re.compile(r'-Token=[a-zA-Z0-9|\-_]+$')
    access_token_regex = re.compile(r'accessToken="[^"]+?"')
    ip_regex = re.compile(r'\.\d{1,3}\.\d{1,3}\.')
    ip_dom_regex = re.compile(r'-\d{1,3}-\d{1,3}-')
    user_regex = re.compile(r'-User=[a-zA-Z0-9|\-_]+([\s&|\'"])+')
    user2_regex = re.compile(r'-User=[a-zA-Z0-9|\-_]+$')
    token_query_regex = re.compile(
        r'(?i)(X-Plex-Token\s*=\s*)[^&\s\'"<>]+'
    )
    token_mapping_regex = re.compile(
        r'(?i)([\'\"]?X-Plex-Token[\'\"]?\s*:\s*[\'\"])[^\'\"]+'
    )
    token_xml_regex = re.compile(
        r'(?is)(<(?:authentication-token|auth_token)>)[^<]*(</(?:authentication-token|auth_token)>)'
    )
    access_token_value_regex = re.compile(
        r'(?i)(accessToken\s*[=:]\s*[\'\"]?)[^\s,}\'\"&<>]+'
    )
    authorization_regex = re.compile(
        r'(?i)([\'\"]?Authorization[\'\"]?\s*:\s*[\'\"]?(?:Basic|Bearer)\s+)[^\s,}\'\"]+'
    )
    temp_token_regex = re.compile(r'(?i)(Temp token is:\s*)\S+')

    def __init__(self, sub=None):

        self.settings = _shared_settings()

        self.main = CONFIG['name']
        self.sub = '.' + sub if sub else ''

        try:
            self.level = self.settings.get_debug()
        except (TypeError, ValueError):
            self.level = self.LOG_DEBUG

        self.privacy = self.settings.privacy()

    def get_name(self, level):
        return self.DEBUG_MAP[level]

    def error(self, message, no_privacy=False):
        return self.__print_message(message, self.LOG_ERROR, no_privacy)

    def notice(self, message, no_privacy=False):
        return self.__print_message(message, self.LOG_NOTICE, no_privacy)

    def debug(self, message, no_privacy=False):
        return self.__print_message(message, self.LOG_DEBUG, no_privacy)

    def debugplus(self, message, no_privacy=False):
        return self.__print_message(message, self.LOG_DEBUGPLUS, no_privacy)

    def __get_kodi_log_level(self, level):
        return self.KODI_LEVELS.get(level, xbmc.LOGDEBUG)

    def _enabled(self, level):
        if self.level == self.LOG_DISABLED:
            return False
        return self.level >= level or level in (self.LOG_ERROR, self.LOG_NOTICE)

    def debug_enabled(self):
        """Whether a debug line would be printed.

        ``__print_message`` drops a line it must not print, but the caller has
        already built it by then.  Anything expensive to put into words - a
        tree serialised back to xml, a dict dumped as json - has to ask first.
        """
        return self._enabled(self.LOG_DEBUG)

    def debugplus_enabled(self):
        return self._enabled(self.LOG_DEBUGPLUS)

    # _caller() -> __print_message() -> error()/notice()/debug()/__call__() -> caller
    CALLER_DEPTH = 3

    @classmethod
    def _caller(cls):
        """
        Name of the function that asked for the log line.

        ``sys._getframe`` is used rather than ``inspect.stack()``: the latter
        walks and materialises the whole stack on every single log call, which
        is by far the most expensive thing this add-on does while browsing.
        """
        try:
            return sys._getframe(cls.CALLER_DEPTH).f_code.co_name  # pylint: disable=protected-access
        except (AttributeError, ValueError):
            return '?'

    def _redact(self, msg):
        try:
            msg = self.token_regex.sub(r'-Token=XXXXXXXXXX\g<1>', msg)
            msg = self.token2_regex.sub(r'-Token=XXXXXXXXXX', msg)
            msg = self.access_token_regex.sub(r'accessToken="XXXXXXXXXX"', msg)
            msg = self.ip_regex.sub(r'.X.X.', msg)
            msg = self.ip_dom_regex.sub(r'-X-X-', msg)
            msg = self.user_regex.sub(r'-User=XXXXXXX\g<1>', msg)
            msg = self.user2_regex.sub(r'-User=XXXXXXX', msg)
        except Exception:  # pylint: disable=broad-except
            return 'Logging failure:\n%s' % traceback.format_exc()

        return msg

    def _redact_secrets(self, msg):
        """Mask credentials even when optional privacy filtering is disabled."""
        try:
            msg = self.token_query_regex.sub(r'\g<1>XXXXXXXXXX', msg)
            msg = self.token_mapping_regex.sub(r'\g<1>XXXXXXXXXX', msg)
            msg = self.token_xml_regex.sub(r'\g<1>XXXXXXXXXX\g<2>', msg)
            msg = self.access_token_value_regex.sub(r'\g<1>XXXXXXXXXX', msg)
            msg = self.authorization_regex.sub(r'\g<1>XXXXXXXXXX', msg)
            msg = self.temp_token_regex.sub(r'\g<1>XXXXXXXXXX', msg)
        except Exception:  # pylint: disable=broad-except
            return 'Logging failure:\n%s' % traceback.format_exc()

        return msg

    def __print_message(self, msg, level=0, no_privacy=False):
        # bail out before doing any formatting or redaction work
        if not self._enabled(level):
            return

        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', 'replace')
        elif not isinstance(msg, str):
            try:
                msg = str(msg)
            except Exception:  # pylint: disable=broad-except
                level = self.LOG_ERROR
                msg = 'Logging failed to coerce \'%s\' message' % type(msg)

        msg = self._redact_secrets(msg)

        if self.privacy and not no_privacy:
            msg = self._redact(msg)

        xbmc.log('%s%s -> %s : %s' % (self.main, self.sub, self._caller(), msg),
                 self.__get_kodi_log_level(level))

    def __call__(self, msg, level=0):
        return self.__print_message(msg, level)
