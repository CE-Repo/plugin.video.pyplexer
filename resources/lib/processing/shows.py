# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from artwork.fanart_tv import prefer_artwork
from artwork.fanart_tv import listing_url_with_guids
from core.common import get_handle
from core.context import Item
from core.utils import get_xml
from gui.builders.show import create_show_item
from processing.pagination import add_page_navigation
from processing.pagination import paged_library_url


def process_shows(context, url, tree=None):
    xbmcplugin.setContent(get_handle(), 'tvshows')

    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_MPAA_RATING)

    # Get the URL and server name.  Get the XML and parse
    request_url = listing_url_with_guids(
        context.settings, paged_library_url(context, url))
    tree = get_xml(context, request_url, tree)
    if tree is None:
        return

    server = context.plex_network.get_server_from_url(url)

    items = []
    append_item = items.append
    # For each directory tag we find
    shows = list(tree.iter('Directory'))
    prefer_artwork(context, shows, 'show', server)

    for show in shows:
        item = Item(server, url, tree, show)
        append_item(create_show_item(context, item))

    add_page_navigation(context, url, tree, items)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
