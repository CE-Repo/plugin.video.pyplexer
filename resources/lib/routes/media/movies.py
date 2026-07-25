# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.movies import process_movies


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_movies(context, url)
