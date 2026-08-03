# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from artwork.fanart_tv import clear_cache as clear_artwork_cache
from plex.network import Plex
from storage.data_cache import DATA_CACHE


def run(context):
    context.plex_network = Plex(context.settings, load=False)
    context.plex_network.delete_cache()
    DATA_CACHE.delete_cache(True)
    clear_artwork_cache()
    xbmc.executebuiltin('Container.Refresh')
