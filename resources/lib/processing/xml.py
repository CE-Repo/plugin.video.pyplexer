# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.constants import MODES
from core.context import GUIItem
from core.context import Item
from core.strings import i18n
from core.utils import get_xml
from gui.builders.common import get_link_url
from gui.builders.episode import create_episode_item
from gui.builders.movie import create_movie_item
from gui.builders.playlist import create_playlist_item
from gui.builders.track import create_track_item
from gui.list_item import create_gui_item


def process_xml(context, url, tree=None):
    """
        Main function to parse plugin XML from PMS
        Will create dir or item links depending on what the
        main tag is.
        @input: plugin page URL
        @return: nothing, creates Kodi GUI listing
    """

    server = context.plex_network.get_server_from_url(url)
    tree = get_xml(context, url, tree)

    if tree is None:
        return

    content_type = 'files'

    items = []
    append_item = items.append

    # .iter includes itself, this is unwanted
    branches = [elem for elem in tree.iter() if elem is not tree]
    for branch in branches:
        details = {}
        if branch.get('title'):
            details['title'] = branch.get('title')

        if not details.get('title'):
            details['title'] = branch.get('name', i18n('Unknown'))

        extra_data = {
            'identifier': tree.get('identifier', ''),
            'type': 'Video'
        }

        _url = get_link_url(server, url, branch)

        if branch.tag in ['Directory', 'Podcast']:
            extra_data['mode'] = MODES.PROCESSXML
            gui_item = GUIItem(_url, details, extra_data)
            append_item(create_gui_item(context, gui_item))

        elif branch.tag == 'Track':
            content_type = 'songs'
            item = Item(server, url, tree, branch)
            append_item(create_track_item(context, item))

        elif branch.tag == 'Playlist':
            item = Item(server, url, tree, branch)
            append_item(create_playlist_item(context, item))

        elif branch.tag == 'Video':
            item = Item(server, url, tree, branch)

            if tree.get('viewGroup') == 'movie':
                content_type = 'movies'
                append_item(create_movie_item(context, item))
                continue

            if tree.get('viewGroup') == 'episode':
                content_type = 'episodes'
                append_item(create_episode_item(context, item))
                continue

            content_type = 'videos'
            append_item(create_movie_item(context, item))

    if items:
        _set_content(content_type)
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())


def _set_content(content_type):
    if content_type == 'files':
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)

    elif content_type == 'songs':
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DURATION)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_SONG_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TRACKNUM)

    elif content_type in ['movies', 'videos']:
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATEADDED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        if content_type != 'videos':
            xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_MPAA_RATING)

    elif content_type == 'episodes':
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATEADDED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_MPAA_RATING)

    xbmcplugin.setContent(get_handle(), content_type)
