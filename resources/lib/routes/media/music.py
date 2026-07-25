# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.music import process_music


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_music(context, url)
