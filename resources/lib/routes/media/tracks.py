# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.tracks import process_tracks


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_tracks(context, url)
