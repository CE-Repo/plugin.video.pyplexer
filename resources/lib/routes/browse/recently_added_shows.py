# -*- coding: utf-8 -*-

"""Recently added episodes, listed as the shows they belong to.

The episode listing of the same name shows every new episode; this one shows
each show once, the way Plex' own 'Recently Added' does, so a season that
lands in one go takes a single row instead of ten.
"""

import xml.etree.ElementTree as ETree
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote

import xbmcplugin  # pylint: disable=import-error

from artwork.fanart_tv import prefer_artwork
from core.common import get_handle
from core.context import Item
from core.logger import Logger
from gui.builders.show import create_show_item
from plex.network import Plex
from processing.pagination import paginate_local_items

LOG = Logger()

MAX_WORKERS = 4


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    size = context.settings.recently_added_item_count()
    hide_watched = not context.settings.recently_added_include_watched()
    wanted_path = _wanted_path(context)

    episodes = []
    for server in _servers(context):
        if server.is_offline():
            continue

        for section in server.get_sections():
            if section.content_type() != 'tvshows':
                continue
            if wanted_path and section.get_path() != wanted_path:
                continue
            episodes += _recently_added(server, section, size, hide_watched)

    items = paginate_local_items(context, _build_items(context, _shows(episodes)))

    if items:
        # the newest addition comes first, which is the point of the listing
        xbmcplugin.addSortMethod(get_handle(), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(get_handle(),
                                 xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
        xbmcplugin.setContent(get_handle(), 'tvshows')
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=False)


def _servers(context):
    """The servers to list, or the single one a widget path names."""
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


def _recently_added(server, section, size, hide_watched):
    try:
        section_key = int(section.get_key())
    except (TypeError, ValueError):
        return []

    tree = server.get_recently_added(section=section_key, size=size,
                                     hide_watched=hide_watched)
    if tree is None:
        return []

    return [(server, episode) for episode in tree.iter('Video')
            if episode.get('type') == 'episode']


def _shows(episodes):
    """One entry per show, in the order its newest episode was added."""
    shows = []
    seen = set()
    for server, episode in episodes:
        rating_key = episode.get('grandparentRatingKey')
        if not rating_key:
            continue

        identity = (server.get_uuid(), rating_key)
        if identity in seen:
            continue

        seen.add(identity)
        shows.append((server, rating_key, episode))

    return shows


def _build_items(context, shows):
    if not shows:
        return []

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(shows))) as executor:
        resolved = list(executor.map(_show_element, shows))

    grouped = {}
    for (server, _, _), (element, _) in zip(shows, resolved):
        grouped.setdefault(server.get_uuid(), (server, []))[1].append(element)

    for server, elements in grouped.values():
        prefer_artwork(context, elements, 'show', server)

    items = []
    for (server, _, _), (element, tree) in zip(shows, resolved):
        item = Item(server, server.get_url_location(), tree, element)
        items.append(create_show_item(context, item))

    return items


def _show_element(show):
    """The show an added episode belongs to, as the library lists it.

    Its own metadata carries the episode counts the watched overlay is built
    from, so it is worth the request; a server that does not answer leaves the
    episode's own view of its show, which is enough to open it.
    """
    server, rating_key, episode = show

    tree = server.get_metadata(rating_key)
    if tree is not None:
        for directory in tree.iter('Directory'):
            if directory.get('type') == 'show':
                return directory, tree

    LOG.debug('No show metadata for %s, using the episode instead' % rating_key)
    element = _show_from_episode(episode)
    container = ETree.Element('MediaContainer')
    container.append(element)
    return element, container


def _show_from_episode(episode):
    return ETree.Element('Directory', {
        'type': 'show',
        'ratingKey': episode.get('grandparentRatingKey', ''),
        'key': '/library/metadata/%s/children' % episode.get('grandparentRatingKey', ''),
        'guid': episode.get('grandparentGuid', ''),
        'title': episode.get('grandparentTitle', ''),
        'titleSort': episode.get('grandparentTitle', ''),
        'thumb': episode.get('grandparentThumb', ''),
        'art': episode.get('grandparentArt', ''),
        'theme': episode.get('grandparentTheme', ''),
    })
