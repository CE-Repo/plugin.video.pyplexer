# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.albums import process_albums


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_albums(context, url)
