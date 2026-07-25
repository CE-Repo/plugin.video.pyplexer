# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from plex.network import Plex
from storage.data_cache import DATA_CACHE


def run(context):
    context.plex_network = Plex(context.settings, load=False)
    context.plex_network.delete_cache()
    DATA_CACHE.delete_cache(True)
    xbmc.executebuiltin('Container.Refresh')
