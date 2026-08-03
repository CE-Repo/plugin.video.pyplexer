# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.utils import get_xml
from gui.builders.music import create_music_item
from processing.pagination import add_page_navigation
from processing.pagination import paged_listing_url


def process_music(context, url, tree=None):
    server = context.plex_network.get_server_from_url(url)

    tree = get_xml(context, paged_listing_url(context, url), tree)
    if tree is None:
        return

    items = []
    append_item = items.append
    branches = tree.iter()

    for music in branches:

        if music.get('key') is None:
            continue

        item = Item(server, url, tree, music)
        append_item(create_music_item(context, item))

    add_page_navigation(context, url, tree, items)

    if items:
        content_type = items[-1][1].getProperty('content_type')
        if not content_type:
            content_type = 'artists'
        xbmcplugin.setContent(get_handle(), content_type)

        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
