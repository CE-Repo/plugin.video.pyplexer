# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.plex_plugins import process_plex_plugins


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_plex_plugins(context, url)
