# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.seasons import process_seasons


def run(context, url, rating_key=None, library=False):
    context.plex_network = Plex(context.settings, load=True)
    process_seasons(context, url, rating_key=rating_key, library=library)
