# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.logger import Logger
from plex.network import Plex
from storage.data_cache import DATA_CACHE

LOG = Logger()


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    if url.startswith('file'):
        LOG.debug('We are playing a local file')
        # Split out the path from the URL
        playback_url = url.split(':', 1)[1]
    elif url.startswith('http'):
        LOG.debug('We are playing a stream')
        if '?' in url:
            server = context.plex_network.get_server_from_url(url)
            playback_url = server.get_formatted_url(url)
        else:
            playback_url = ''
    else:
        playback_url = url

    list_item = xbmcgui.ListItem(path=playback_url, offscreen=True)

    xbmcplugin.setResolvedUrl(get_handle(), playback_url != '', list_item)
    DATA_CACHE.delete_cache(True)
