# -*- coding: utf-8 -*-

"""A random pick of titles from the movie or show libraries."""

import random
from urllib.parse import unquote

import xbmcplugin  # pylint: disable=import-error

from artwork.fanart_tv import prefer_artwork
from core.common import get_handle
from core.constants import MODES
from core.context import Item
from core.logger import Logger
from gui.builders.movie import create_movie_item
from gui.builders.show import create_show_item
from plex.network import Plex
from processing.pagination import paginate_local_items

LOG = Logger()

_CONTENT_TYPES = {
    'movie': 'movies',
    'show': 'tvshows',
}


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    section_type = _section_type(context)
    if not section_type:
        xbmcplugin.endOfDirectory(get_handle(), succeeded=False, cacheToDisc=False)
        return

    sample_size = _sample_size(context)
    wanted_path = _wanted_path(context)

    entries = []
    for server in _servers(context):
        if server.is_offline():
            continue

        for section in server.get_sections():
            if section.get_type() != section_type:
                continue
            if wanted_path and section.get_path() != wanted_path:
                continue
            entries += _sample_section(server, section, sample_size)

    # every library contributed its own sample, so they are shuffled once more
    # together - otherwise the listing would run library by library
    random.shuffle(entries)

    items = paginate_local_items(context, _build_items(context, entries))

    if items:
        # the order is the point of this listing, so Kodi is given nothing to
        # re-sort it by
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.setContent(get_handle(), _CONTENT_TYPES[section_type])
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=False)


def _section_type(context):
    try:
        mode = int(context.params.get('mode', MODES.UNSET))
    except (TypeError, ValueError):
        return ''

    if mode == MODES.MOVIES_RANDOM:
        return 'movie'

    if mode == MODES.TVSHOWS_RANDOM:
        return 'show'

    return ''


def _servers(context):
    """The servers to sample, or the single one a widget path names."""
    server_uuid = context.params.get('server_uuid')
    if server_uuid:
        server = context.plex_network.get_server_from_uuid(server_uuid)
        return [server] if server else []

    server_list = context.plex_network.get_active_server_list()
    LOG.debug('Using list of %s servers: %s' % (len(server_list), server_list))
    return server_list


def _wanted_path(context):
    """The one library a widget asked for, empty for all of them."""
    path = unquote(context.params.get('url') or '')
    if path.startswith('/library/sections/'):
        return path
    return ''


def _sample_size(context):
    try:
        return max(1, context.settings.random_item_count())
    except (TypeError, ValueError):
        return 25


def _section_id(section):
    for part in section.get_path().split('/'):
        if part.isdigit():
            return int(part)
    return None


def _sample_section(server, section, size):
    section_id = _section_id(section)
    if section_id is None:
        return []

    start = _random_start(server, section_id, size)
    tree = server.get_random(section=section_id, start=start, size=size)
    if tree is None:
        # a server that does not know the random sort still answers a plain
        # window, which the random offset above has already moved about
        LOG.debug('Section %s did not answer a random listing, using a window'
                  % section_id)
        tree = server.get_section_all(section=section_id, start=start, size=size)

    if tree is None:
        return []

    tag = 'Video' if section.is_movie() else 'Directory'
    return [(server, tree, element) for element in tree.iter(tag)]


def _random_start(server, section_id, size):
    """Where in the section the requested window starts.

    ``sort=random`` makes the offset irrelevant, but a server that ignores the
    sort would hand out the same first titles on every visit; a random offset
    keeps those listings varied too.  The total comes from a single-item
    request, so every visit after the first is answered from the data cache.
    """
    tree = server.get_section_all(section=section_id, start=0, size=1)
    if tree is None:
        return 0

    try:
        total = int(tree.get('totalSize') or tree.get('size') or 0)
    except (TypeError, ValueError):
        total = 0

    if total <= size:
        return 0

    return random.randint(0, total - size)


def _build_items(context, entries):
    """Build the list items, keeping the shuffled order of ``entries``.

    Artwork is resolved per server first, since ``prefer_artwork`` batches its
    lookups and writes what it finds back onto the elements themselves.
    """
    grouped = {}
    for server, _, content in entries:
        grouped.setdefault(server.get_uuid(), (server, []))[1].append(content)

    for server, elements in grouped.values():
        movies = [element for element in elements if element.get('type') == 'movie']
        shows = [element for element in elements if element.get('type') == 'show']
        prefer_artwork(context, movies, 'movie', server)
        prefer_artwork(context, shows, 'show', server)

    items = []
    for server, tree, content in entries:
        item = Item(server, server.get_url_location(), tree, content)
        if content.get('type') == 'movie':
            items.append(create_movie_item(context, item))
        elif content.get('type') == 'show':
            items.append(create_show_item(context, item))

    return items
