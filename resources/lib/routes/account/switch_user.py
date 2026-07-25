# -*- coding: utf-8 -*-

from core.logger import Logger
from plex.network import Plex
from plex.signin import switch_user
from storage.data_cache import DATA_CACHE

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=False)
    _ = switch_user(context)
    context.plex_network.delete_cache()
    DATA_CACHE.delete_cache(True)
