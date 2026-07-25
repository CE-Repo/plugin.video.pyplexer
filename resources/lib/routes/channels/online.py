# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.plex_online import process_plex_online


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_plex_online(context, url)
