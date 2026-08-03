# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.logger import Logger
from core.utils import attach_media_streams
from core.utils import get_xml
from gui.builders.episode import create_episode_item
from processing.pagination import add_page_navigation
from processing.pagination import paged_library_url

LOG = Logger()


def process_episodes(context, url, tree=None, rating_key=None, library=False):
    xbmcplugin.setContent(get_handle(), 'episodes')

    if not url.startswith(('http', 'file')) and rating_key:
        # Get URL, XML and parse
        server = context.plex_network.get_server_from_uuid(url)
        url = server.join_url(server.get_url_location(),
                              'library/metadata/%s/children' % str(rating_key))
    else:
        server = context.plex_network.get_server_from_url(url)

    tree = get_xml(context, paged_library_url(context, url), tree)
    if tree is None:
        return

    if tree.get('mixedParents') == '1' or context.settings.episode_sort_method() == 'plex':
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    else:
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_EPISODE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)

    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATEADDED)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RATING)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_MPAA_RATING)

    items = []
    append_item = items.append
    episodes = list(tree.iter('Video'))

    # a season fits in one lookup, so the flags say Dolby Vision Profile 7 and
    # not just Dolby Vision
    attach_media_streams(server, episodes)

    for episode in episodes:
        item = Item(server, url, tree, episode)
        append_item(create_episode_item(context, item, library=library))

    add_page_navigation(context, url, tree, items)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
