# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.common import get_argv
from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n_or
from plex.network import Plex
from storage.data_cache import DATA_CACHE

LOG = Logger()


def remove(context):
    """Drop the selected item from the server's Continue Watching hub."""
    context.plex_network = Plex(context.settings, load=True)

    argv = get_argv()
    server_identifier = argv[2] if len(argv) > 2 else ''
    metadata_id = argv[3] if len(argv) > 3 else ''

    if server_identifier.startswith('http'):
        server = context.plex_network.get_server_from_url(server_identifier)
    else:
        server = context.plex_network.get_server_from_uuid(server_identifier)

    LOG.debug('Removing %s from Continue Watching' % metadata_id)

    success = server is not None and metadata_id and \
        server.remove_from_continue_watching(metadata_id)

    if success:
        message = i18n_or('Removed from Continue Watching',
                          'Aus „Fortsetzen“ entfernt')
    else:
        message = i18n_or('Could not remove from Continue Watching',
                          'Konnte nicht aus „Fortsetzen“ entfernt werden')

    xbmcgui.Dialog().notification(heading=CONFIG['name'], message=message,
                                  icon=CONFIG['icon'])

    if success:
        DATA_CACHE.delete_cache(True)
        xbmc.executebuiltin('Container.Refresh')
