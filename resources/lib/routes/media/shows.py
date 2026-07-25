# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.shows import process_shows


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_shows(context, url)
