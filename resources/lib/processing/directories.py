# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.logger import Logger
from gui.builders.directory import create_directory_item
from processing.pagination import add_page_navigation

LOG = Logger()


def process_directories(context, url, tree=None):
    LOG.debug('Processing secondary menus')

    content_type = 'files'
    if '/collection' in url:
        content_type = 'sets'

    xbmcplugin.setContent(get_handle(), content_type)

    server = context.plex_network.get_server_from_url(url)

    items = []
    append_item = items.append
    directories = tree.iter('Directory')

    for directory in directories:
        item = Item(server, url, tree, directory)
        append_item(create_directory_item(context, item))

    add_page_navigation(context, url, tree, items)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
