# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.common import get_argv
from core.logger import Logger
from core.strings import i18n
from plex.network import Plex
from storage.data_cache import DATA_CACHE

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    server_uuid = get_argv()[2]
    metadata_id = get_argv()[3]

    server = context.plex_network.get_server_from_uuid(server_uuid)

    result = xbmcgui.Dialog().yesno(i18n('Confirm playlist delete?'),
                                    i18n('Are you sure you want to delete this playlist?'))
    if result:
        _ = server.delete_playlist(metadata_id)
        DATA_CACHE.delete_cache(True)
        xbmc.executebuiltin('Container.Refresh')
