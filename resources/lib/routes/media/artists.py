# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.artists import process_artists


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_artists(context, url)
