# -*- coding: utf-8 -*-

from core.logger import Logger
from plex.network import Plex
from plex.signin import sign_in_to_plex
from storage.data_cache import DATA_CACHE

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=False)
    _ = sign_in_to_plex(context)
    context.plex_network.delete_cache()
    DATA_CACHE.delete_cache(True)
