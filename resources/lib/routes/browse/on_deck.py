# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from artwork.fanart_tv import prefer_artwork
from artwork.fanart_tv import prefer_episode_artwork
from core.common import get_handle
from core.context import Item
from core.logger import Logger
from gui.builders.episode import create_episode_item
from gui.builders.movie import create_movie_item
from plex.network import Plex
from playback.quality import media_details
from playback.quality import quality_score
from processing.pagination import paginate_local_items

LOG = Logger()

_ON_DECK_CONTENT_TYPES = ('movies', 'tvshows')


def run(context):
    context.plex_network = Plex(context.settings, load=True)
    content_type = context.params.get('content_type')
    server_list = context.plex_network.get_active_server_list()

    entries = []
    LOG.debug('Using list of %s servers: %s' % (len(server_list), server_list))
    for server in server_list:
        sections = server.get_sections()
        for section in sections:
            # a mixed listing (content_type is None) takes both movie and
            # show sections; a single-type listing keeps its own filter
            if content_type is None:
                wanted = section.content_type() in _ON_DECK_CONTENT_TYPES
            else:
                wanted = section.content_type() == content_type
            if wanted:
                entries += _fetch_section(server, int(section.get_key()))

    entries = _deduplicate(entries)
    items = paginate_local_items(context, _build_items(context, entries))

    if items:
        xbmcplugin.setContent(get_handle(), content_type or 'videos')
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=False)


def _fetch_section(server, section):
    tree = server.get_ondeck(section=section)
    if tree is None:
        return []
    return [(server, tree, content) for content in tree.iter('Video')]


def _identity(content):
    """A key that is the same for two library copies of the same title.

    A user who keeps a 1080p and a 4K copy of a film in separate library
    sections (a common split) gets the same film twice in on deck otherwise,
    since each copy is its own Plex item with its own watch progress. Plex's
    own 'guid' (the metadata agent match) is identical for both copies; only
    an unmatched item without one falls back to its plain attributes.
    """
    guid = content.get('guid')
    if guid:
        return guid
    return (content.get('type'), content.get('title'), content.get('year'),
           content.get('grandparentTitle'), content.get('parentIndex'),
           content.get('index'))


def _best_quality(content):
    """Sort key for the best <Media> version a Plex item carries, so a 4K
    copy is recognised as better than a 1080p copy of the same title."""
    scores = [quality_score(media_details(media)) for media in content.iter('Media')]
    return max(scores) if scores else ()


def _deduplicate(entries):
    """Keep one entry per title; when two library copies collide, keep the
    entry whose best version has the higher quality (e.g. the 4K copy over
    the 1080p copy), not just whichever section was scanned first."""
    best = {}
    order = []
    for entry in entries:
        key = _identity(entry[2])
        if key not in best:
            order.append(key)
            best[key] = entry
        elif _best_quality(entry[2]) > _best_quality(best[key][2]):
            best[key] = entry
    return [best[key] for key in order]


def _build_items(context, entries):
    servers = {}
    grouped = {}
    for server, tree, content in entries:
        uuid = server.get_uuid()
        servers[uuid] = server
        grouped.setdefault(uuid, []).append((tree, content))

    items = []
    append_item = items.append

    for uuid, group in grouped.items():
        server = servers[uuid]
        episodes = [content for _, content in group if content.get('type') == 'episode']
        movies = [content for _, content in group if content.get('type') == 'movie']
        prefer_artwork(context, movies, 'movie', server)
        prefer_episode_artwork(context, episodes, server)

        for tree, content in group:
            item = Item(server, server.get_url_location(), tree, content)
            if content.get('type') == 'episode':
                append_item(create_episode_item(context, item))
            elif content.get('type') == 'movie':
                append_item(create_movie_item(context, item))

    return items
