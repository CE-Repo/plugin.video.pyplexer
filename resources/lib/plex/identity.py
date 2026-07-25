# -*- coding: utf-8 -*-

import platform
import sys
import uuid
from contextlib import closing

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error
import xbmcvfs  # pylint: disable=import-error

from core.common import get_platform
from core.constants import CONFIG

# Session cache (home-window property) for the Plex Media Server metadata
# language. Filled in by the network layer once the server libraries are known.
METADATA_LANGUAGE_PROPERTY = '%s-metadata-language' % CONFIG['id']


def get_metadata_language():
    """The metadata language to request from Plex (X-Plex-Language).

    Uses the language configured on the user's Plex Media Server libraries when
    it has been resolved; otherwise falls back to English.
    """
    return xbmcgui.Window(10000).getProperty(METADATA_LANGUAGE_PROPERTY) or 'en'


def get_device_name(settings, device_name):
    if device_name is None:
        device_name = settings.device_name()
    return device_name


def get_client_identifier(settings, client_id):
    if client_id is None:
        client_id = settings.client_id()

        if not client_id:
            client_id = str(uuid.uuid4())
            settings.set_client_id(client_id)

    return client_id


def create_plex_identification(settings, device_name=None, client_id=None, user=None, token=None):
    headers = {
        'X-Plex-Device': get_device(),
        'X-Plex-Client-Platform': 'Kodi',
        'X-Plex-Device-Name': get_device_name(settings, device_name),
        'X-Plex-Language': get_metadata_language(),
        'X-Plex-Platform': get_platform(),
        'X-Plex-Client-Identifier': get_client_identifier(settings, client_id),
        'X-Plex-Product': CONFIG['name'],
        'X-Plex-Platform-Version': platform.uname()[2],
        'X-Plex-Version': CONFIG['version'],
        'X-Plex-Provides': 'player,controller'
    }

    if token is not None:
        headers['X-Plex-Token'] = token

    if user is not None:
        headers['X-Plex-User'] = user

    return headers


def get_device():
    device = None
    if xbmc.getCondVisibility('system.platform.windows'):
        device = 'Windows'
    if xbmc.getCondVisibility('system.platform.linux') \
            and not xbmc.getCondVisibility('system.platform.android'):
        device = 'Linux'
    if xbmc.getCondVisibility('system.platform.osx'):
        device = 'Darwin'
    if xbmc.getCondVisibility('system.platform.android'):
        device = 'Android'

    if xbmcvfs.exists('/proc/device-tree/model'):
        with closing(xbmcvfs.File('/proc/device-tree/model')) as open_file:
            if 'Raspberry Pi' in open_file.read():
                device = 'Raspberry Pi'

    if xbmcvfs.exists('/etc/os-release'):
        with closing(xbmcvfs.File('/etc/os-release')) as open_file:
            contents = open_file.read()
            if 'libreelec' in contents:
                device = 'LibreELEC'
            if 'osmc' in contents:
                device = 'OSMC'

    if device is None:
        try:
            device = platform.system()
        except (AttributeError, OSError):
            try:
                device = platform.platform(terse=True)
            except (AttributeError, OSError):
                device = sys.platform

    return device
