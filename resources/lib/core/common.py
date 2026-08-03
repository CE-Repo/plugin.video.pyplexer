# -*- coding: utf-8 -*-

import socket
import sys
from urllib.parse import unquote
from urllib.parse import urlencode

import xbmc  # pylint: disable=import-error

from core.constants import COMMANDS
from core.constants import CONFIG
from core.logger import Logger

LOG = Logger()


def get_argv():
    return sys.argv


def get_current_plugin_url():
    """Return the full URL of the currently rendered plugin container."""
    argv = get_argv()
    if not argv:
        return ''

    query = argv[2] if len(argv) > 2 else ''
    return argv[0] + query


def get_handle():
    try:
        return int(get_argv()[1])
    except (ValueError, IndexError):
        return -1


def get_params():
    try:
        param_string = get_argv()[2]
    except IndexError:
        param_string = ''

    params = parse_query_string(param_string)

    params['url'] = params.get('url')  # ensure the key always exists
    params['command'] = _get_command_parameter(params['url'])
    params['path_mode'] = get_plugin_url_path()

    LOG.debug('Parameters |%s| -> |%s|' % (param_string, str(params)))
    return params


def parse_query_string(param_string):
    """
    Decode the query string Kodi hands the add-on in ``sys.argv[2]``.

    ``urllib.parse.parse_qsl`` is deliberately not used: the add-on builds its
    URLs with ``quote()`` (not ``quote_plus()``), so a literal ``+`` must
    survive the round trip instead of turning into a space.
    """
    params = {}

    for pair in param_string.lstrip('?').split('&'):
        if not pair:
            continue

        name, separator, value = pair.partition('=')
        if not separator:
            continue

        params[unquote(name)] = unquote(value)

    return params


def _get_command_parameter(url):
    command = None
    if url and url.startswith('cmd'):
        try:
            command = url.split(':')[1]
        except IndexError:
            command = None

    if command is None:
        try:
            command = get_argv()[1]
        except IndexError:
            pass

    try:
        int(command)
    except (ValueError, TypeError):
        return command

    # a numeric argv[1] is the plugin handle, not a command
    return COMMANDS.UNSET


def is_resuming_video():
    try:
        resume_argument = get_argv()[3].split(':')
    except IndexError:
        return False

    return resume_argument[:2] == ['resume', 'true']


def get_plugin_url_path():
    plugin_url = get_argv()[0]
    path = plugin_url.replace('plugin://%s/' % CONFIG['id'], '').rstrip('/')
    if not path or (path and path.endswith('.py')):
        return None
    return path


def get_plugin_url(params):
    return 'plugin://%s/?%s' % (CONFIG['id'], urlencode(params))


def is_ip(address):
    """True if ``address`` is a literal IPv4 or IPv6 address."""
    if not address:
        return False

    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, address)
            return True
        except (OSError, ValueError):
            continue

    return False


def get_platform_ip():
    return xbmc.getIPAddress()


# Ordered from least to most specific: several of these conditions are true at
# the same time (a Raspberry Pi is also Linux, Android is also Linux, iOS is
# also Darwin), so the most specific match has to be tested last and win.
PLATFORMS = (
    ('system.platform.linux', 'Linux'),
    ('system.platform.windows', 'Windows'),
    ('system.platform.osx', 'MacOSX'),
    ('system.platform.android', 'Android'),
    ('system.platform.raspberrypi', 'RaspberryPi'),
    ('system.platform.ios', 'iOS'),
    ('system.platform.tvos', 'tvOS'),
    ('system.platform.atv2', 'AppleTV2'),
)


def get_platform():
    platform = 'Unknown'

    for condition, name in PLATFORMS:
        if xbmc.getCondVisibility(condition):
            platform = name

    return platform
