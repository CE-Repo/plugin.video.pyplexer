# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ETree

import xbmc  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from artwork.fanart_tv import prefer_artwork
from artwork.fanart_tv import prefer_episode_artwork
from core.common import get_handle
from core.constants import MODES
from core.context import Item
from core.logger import Logger
from core.strings import i18n
from gui.builders.album import create_album_item
from gui.builders.artist import create_artist_item
from gui.builders.episode import create_episode_item
from gui.builders.movie import create_movie_item
from gui.builders.show import create_show_item
from gui.builders.track import create_track_item
from plex.network import Plex
from processing.pagination import UNLIMITED
from processing.pagination import add_page_navigation
from processing.pagination import page_number
from processing.pagination import page_size

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    context.params['query'] = (context.params.get('query') or
                               _get_search_query())
    if not context.params['query']:
        xbmcplugin.endOfDirectory(get_handle(), succeeded=False, cacheToDisc=False)
        return

    all_sections = context.plex_network.active_sections()
    LOG.debug('Using list of %s sections: %s' % (len(all_sections), all_sections))

    items, total = search(context, all_sections)

    container = ETree.Element('MediaContainer', {
        'size': str(len(items)),
        'totalSize': str(total),
    })
    add_page_navigation(context, 'http://pyplexer/search', container, items)

    if items:
        content_type = get_content_type(context)
        add_sort_methods(content_type)
        xbmcplugin.setContent(get_handle(), content_type)
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=False)


def add_sort_methods(content_type):
    if content_type == 'movies':
        xbmcplugin.addSortMethod(get_handle(),
                                 xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATEADDED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_MPAA_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    elif content_type == 'tvshows':
        xbmcplugin.addSortMethod(get_handle(),
                                 xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_MPAA_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    elif content_type == 'episodes':
        xbmcplugin.addSortMethod(get_handle(),
                                 xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_EPISODE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATEADDED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_MPAA_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    elif content_type == 'albums':
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_ALBUM_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_ARTIST_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_LASTPLAYED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    elif content_type == 'artists':
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_ARTIST_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_LASTPLAYED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    elif content_type == 'songs':
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_SONG_RATING)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_TRACKNUM)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DURATION)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    else:
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_VIDEO_YEAR)


def get_section_type(context):
    mode = int(context.params.get('mode', -1))

    if mode == MODES.MOVIES_SEARCH_ALL:
        return 'movie'

    if mode == MODES.TVSHOWS_SEARCH_ALL:
        return 'show'

    if mode == MODES.EPISODES_SEARCH_ALL:
        return 'show'

    if mode == MODES.ARTISTS_SEARCH_ALL:
        return 'artist'

    if mode == MODES.ALBUMS_SEARCH_ALL:
        return 'artist'

    if mode == MODES.TRACKS_SEARCH_ALL:
        return 'artist'

    return ''


def get_item_type(context):
    """
    {'movie': 1, 'show': 2, 'season': 3, 'episode': 4, 'trailer': 5, 'comic': 6, 'person': 7,
     'artist': 8, 'album': 9, 'track': 10, 'picture': 11, 'clip': 12, 'photo': 13, 'photoalbum': 14,
     'playlist': 15, 'playlistFolder': 16, 'collection': 18, 'userPlaylistItem': 1001}
    """
    mode = int(context.params.get('mode', -1))

    if mode == MODES.MOVIES_SEARCH_ALL:
        return 1

    if mode == MODES.TVSHOWS_SEARCH_ALL:
        return 2

    if mode == MODES.EPISODES_SEARCH_ALL:
        return 4

    if mode == MODES.ARTISTS_SEARCH_ALL:
        return 8

    if mode == MODES.ALBUMS_SEARCH_ALL:
        return 9

    if mode == MODES.TRACKS_SEARCH_ALL:
        return 10

    return -1


def get_content_type(context):
    mode = int(context.params.get('mode', -1))

    if mode == MODES.MOVIES_SEARCH_ALL:
        return 'movies'

    if mode == MODES.TVSHOWS_SEARCH_ALL:
        return 'tvshows'

    if mode == MODES.EPISODES_SEARCH_ALL:
        return 'episodes'

    if mode == MODES.ARTISTS_SEARCH_ALL:
        return 'artists'

    if mode == MODES.ALBUMS_SEARCH_ALL:
        return 'albums'

    if mode == MODES.TRACKS_SEARCH_ALL:
        return 'songs'

    return 'files'


def search(context, sections):
    results = []
    total = 0
    page_limit = page_size()
    skip = (page_number(context) - 1) * page_limit
    remaining = page_limit
    section_type = get_section_type(context)

    for section in sections:
        if section.get_type() == section_type:
            section_items, section_total = _list_content(
                context,
                context.plex_network.get_server_from_uuid(section.get_server_uuid()),
                section.get_path(),
                skip,
                max(1, remaining) if page_limit else UNLIMITED
            )
            total += section_total

            if skip >= section_total:
                skip -= section_total
                continue

            skip = 0
            if not page_limit:
                results += section_items
            elif remaining:
                results += section_items[:remaining]
                remaining -= min(remaining, len(section_items))

    return results, total


def _get_search_query():
    text = ''
    keyboard = xbmc.Keyboard('', i18n('Search...'))
    keyboard.setHeading(i18n('Enter search term'))
    keyboard.doModal()

    if keyboard.isConfirmed():
        text = keyboard.getText()
        if not text.strip():
            return ''

    LOG.debug('Search term input: %s' % text)
    return text.strip()


def _list_content(context, server, section, start, size):
    section_id = [int(part) for part in section.split('/') if part.isdigit()][0]
    item_type = get_item_type(context)

    tree = server.get_search(context.params['query'], item_type,
                             section=section_id, start=start, size=size)
    if tree is None:
        return [], 0

    try:
        total = int(tree.get('totalSize') or tree.get('size') or 0)
    except (TypeError, ValueError):
        total = 0

    iter_types = {
        1: 'Video',
        2: 'Directory',
        4: 'Video',
        8: 'Directory',
        9: 'Directory',
        10: 'Track'
    }

    branches = list(tree.iter(iter_types.get(item_type, 'Directory')))

    if not branches:
        return [], total

    if item_type in (1, 2):
        prefer_artwork(context, branches, 'movie' if item_type == 1 else 'show', server)
    elif item_type == 4:
        prefer_episode_artwork(context, branches, server)

    items = []
    for content in branches:
        item = Item(server, server.get_url_location(), tree, content)
        if content.get('type') == 'show':
            items.append(create_show_item(context, item))

        elif content.get('type') == 'episode':
            items.append(create_episode_item(context, item))

        elif content.get('type') == 'movie':
            items.append(create_movie_item(context, item))

        elif content.get('type') == 'album':
            items.append(create_album_item(context, item))

        elif content.get('type') == 'artist':
            items.append(create_artist_item(context, item))

        elif content.get('type') == 'track':
            items.append(create_track_item(context, item))

    return items, max(total, start + len(items))
