# -*- coding: utf-8 -*-

from plex.network import Plex
from plex.signin import sign_out
from storage.data_cache import DATA_CACHE


def run(context):
    context.plex_network = Plex(context.settings, load=False)
    sign_out(context)
    context.plex_network.delete_cache()
    DATA_CACHE.delete_cache(True)
