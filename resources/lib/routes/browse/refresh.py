# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from storage.data_cache import DATA_CACHE


def run(context):
    if context.settings.cache_clear_on_refresh():
        DATA_CACHE.delete_cache(True)
    xbmc.executebuiltin('Container.Refresh')
