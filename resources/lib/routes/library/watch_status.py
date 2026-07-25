# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from core.common import get_argv
from core.logger import Logger
from plex.network import Plex
from storage.data_cache import DATA_CACHE

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    server_uuid = get_argv()[2]
    metadata_id = get_argv()[3]
    try:
        watch_status = get_argv()[4]
    except IndexError:
        watch_status = 'watch'

    if server_uuid.startswith('http'):
        server = context.plex_network.get_server_from_url(server_uuid)
    else:
        server = context.plex_network.get_server_from_uuid(server_uuid)

    if watch_status == 'watch':
        LOG.debug('Marking %s as watched' % metadata_id)
        server.mark_item_watched(metadata_id)
    else:
        LOG.debug('Marking %s as unwatched' % metadata_id)
        server.mark_item_unwatched(metadata_id)

    DATA_CACHE.delete_cache(True)

    xbmc.executebuiltin('Container.Refresh')
