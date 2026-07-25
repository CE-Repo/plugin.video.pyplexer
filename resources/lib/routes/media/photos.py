# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.photos import process_photos


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_photos(context, url)
