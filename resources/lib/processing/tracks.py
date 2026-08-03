# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.utils import get_xml
from gui.builders.movie import create_movie_item
from gui.builders.photo import create_photo_item
from gui.builders.track import create_track_item
from processing.pagination import add_page_navigation
from processing.pagination import paged_library_url


def process_tracks(context, url, tree=None):
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DURATION)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_SONG_RATING)
    xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TRACKNUM)

    tree = get_xml(context, paged_library_url(context, url), tree)
    if tree is None:
        return

    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()

    server = context.plex_network.get_server_from_url(url)

    content_counter = {
        'photo': 0,
        'track': 0,
        'video': 0,
    }
    items = []
    append_item = items.append
    branches = tree.iter()

    for branch in branches:
        tag = branch.tag.lower()
        item = Item(server, url, tree, branch)
        if tag == 'track':
            append_item(create_track_item(context, item))
        elif tag == 'photo':  # mixed content audio playlist
            append_item(create_photo_item(context, item))
        elif tag == 'video':  # mixed content audio playlist
            append_item(create_movie_item(context, item))

        if isinstance(content_counter.get(tag), int):
            content_counter[tag] += 1

    add_page_navigation(context, url, tree, items)

    if items:
        content_type = 'songs'
        if context.settings.mixed_content_type() == 'majority':
            majority = max(content_counter, key=content_counter.get)
            if majority == 'photo':
                content_type = 'images'
            elif majority == 'video':
                content_type = 'movies'

        xbmcplugin.setContent(get_handle(), content_type)
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
