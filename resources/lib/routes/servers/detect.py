# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
from plex.network import Plex


def run(context):
    context.plex_network = Plex(context.settings, load=False)
    context.plex_network.delete_cache()
    xbmc.executebuiltin('Container.Refresh')
