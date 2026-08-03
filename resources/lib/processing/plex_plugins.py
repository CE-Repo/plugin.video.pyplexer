# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.logger import Logger
from core.utils import get_master_server
from core.utils import get_xml
from gui.builders.plex_plugin import create_plex_plugin_item
from processing.pagination import add_page_navigation
from processing.pagination import paged_listing_url

LOG = Logger()


def process_plex_plugins(context, url, tree=None):
    """
        Main function to parse plugin XML from PMS
        Will create dir or item links depending on what the
        main tag is.
        @input: plugin page URL
        @return: nothing, creates Kodi GUI listing
    """
    xbmcplugin.setContent(get_handle(), 'files')

    server = context.plex_network.get_server_from_url(url)
    tree = get_xml(context, paged_listing_url(context, url), tree)
    if tree is None:
        return

    if (tree.get('identifier') != 'com.plexapp.plugins.myplex') and ('node.plexapp.com' in url):
        LOG.debug('This is a myPlex URL, attempting to locate master server')
        server = get_master_server(context)

    items = []
    append_item = items.append
    plugins = tree.iter()

    for plugin in plugins:
        item = Item(server, tree, url, plugin)
        item = create_plex_plugin_item(context, item)
        if item:
            append_item(item)

    add_page_navigation(context, url, tree, items)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
