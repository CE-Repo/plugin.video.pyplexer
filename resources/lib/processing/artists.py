# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.utils import get_xml
from gui.builders.artist import create_artist_item
from processing.pagination import add_page_navigation
from processing.pagination import paged_library_url


def process_artists(context, url, tree=None):
    """
        Process artist XML and display data
        @input: url of XML page, or existing tree of XML page
        @return: nothing
    """
    xbmcplugin.setContent(get_handle(), 'artists')

    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_ARTIST_IGNORE_THE)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_LASTPLAYED)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)

    # Get the URL and server name.  Get the XML and parse
    tree = get_xml(context, paged_library_url(context, url), tree)
    if tree is None:
        return

    server = context.plex_network.get_server_from_url(url)

    items = []
    append_item = items.append
    artists = tree.iter('Directory')

    for artist in artists:
        item = Item(server, url, tree, artist)
        append_item(create_artist_item(context, item))

    add_page_navigation(context, url, tree, items)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
