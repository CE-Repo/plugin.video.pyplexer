# -*- coding: utf-8 -*-

from plex.network import Plex
from processing.xml import process_xml


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    process_xml(context, url)
