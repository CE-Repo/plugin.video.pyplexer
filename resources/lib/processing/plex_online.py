# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.utils import get_xml
from gui.builders.plex_online import create_plex_online_item


def process_plex_online(context, url):
    xbmcplugin.setContent(get_handle(), 'files')

    server = context.plex_network.get_server_from_url(url)

    tree = get_xml(context, url)
    if tree is None:
        return

    items = []
    append_item = items.append
    plugins = tree.iter()

    for plugin in plugins:
        item = Item(server, url, tree, plugin)
        item = create_plex_online_item(context, item)
        if item:
            append_item(item)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
