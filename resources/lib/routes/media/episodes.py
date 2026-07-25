# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.episodes import process_episodes


def run(context, url, rating_key=None, library=False):
    context.plex_network = Plex(context.settings, load=True)
    process_episodes(context, url, rating_key=rating_key, library=library)
