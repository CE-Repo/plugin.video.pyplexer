# -*- coding: utf-8 -*-

"""Render Plex account-provider content (Watchlist / Discover).

These items come from plex.tv providers (metadata/discover.provider.plex.tv) and
are NOT tied to a specific Plex Media Server, so they are shown as a browsable
listing (posters + metadata) rather than being played directly. Containers
(hubs, shows, seasons) become folders that drill deeper via MODES.PROVIDERBROWSE.
"""

from urllib.parse import quote

import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from infotagger.listitem import ListItemInfoTag  # pylint: disable=import-error

from core.common import get_argv
from core.common import get_handle
from core.constants import COMMANDS
from core.constants import CONFIG
from core.constants import MODES
from core.logger import Logger
from core.strings import i18n
from core.strings import i18n_or
from gui.builders.common import get_media_data

LOG = Logger()

# node types / tags that are containers the user can drill into
_FOLDER_TYPES = ('show', 'season', 'artist', 'album')
_FOLDER_TAGS = ('Hub', 'Directory', 'Playlist')
_CONTENT_TAGS = ('Hub', 'Directory', 'Playlist', 'Video')

_MEDIATYPES = {
    'movie': 'movie',
    'show': 'tvshow',
    'season': 'season',
    'episode': 'episode',
}


def process_provider(context, base, tree, in_watchlist=False):
    """Build a Kodi listing from a provider MediaContainer tree."""
    xbmcplugin.setContent(get_handle(), 'videos')

    if tree is None:
        xbmcplugin.endOfDirectory(get_handle(), succeeded=True,
                                  cacheToDisc=context.settings.cache_directory())
        return

    token = context.plex_network.get_provider_token()

    items = []
    for node in _iter_nodes(tree):
        entry = _build_item(base, token, node, in_watchlist)
        if entry:
            items.append(entry)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(),
                              cacheToDisc=context.settings.cache_directory())


def _iter_nodes(tree):
    for node in list(tree):
        if node.tag in _CONTENT_TAGS:
            yield node


def _build_item(base, token, node, in_watchlist=False):
    title = node.get('title') or node.get('grandparentTitle') or i18n('Unknown')
    node_type = (node.get('type') or '').lower()
    is_folder = node.tag in _FOLDER_TAGS or node_type in _FOLDER_TYPES

    list_item = xbmcgui.ListItem(label=title, offscreen=True)

    art = _art(base, token, node)
    if art:
        list_item.setArt(art)

    info_tag = ListItemInfoTag(list_item, 'video')
    info_tag.set_info(_info_labels(title, node_type, node))

    media = node.find('Media')
    if media is not None:
        stream_info = get_media_data(dict(media.items())).get('stream_info', {})
        info_tag.add_stream_info('video', stream_info.get('video', {}))
        info_tag.add_stream_info('audio', stream_info.get('audio', {}))

    _add_watchlist_context_menu(list_item, node, in_watchlist)

    if is_folder:
        drill = _drill_url(base, node)
        if not drill:
            return None
        url = '%s?mode=%s&url=%s' % (get_argv()[0], MODES.PROVIDERBROWSE,
                                     quote(drill, safe=''))
        return url, list_item, True

    guid = node.get('guid')
    key = node.get('key')
    detail_url = None
    if key:
        detail_url = key if key.startswith('http') else base + key

    # Clips (trailers / extras) are Plex-hosted: stream them straight from the
    # provider instead of trying to match them on the user's servers.
    if node_type == 'clip':
        stream = _direct_stream_url(base, token, node)
        if stream:
            list_item.setProperty('IsPlayable', 'true')
            return stream, list_item, False
        if detail_url:
            list_item.setProperty('IsPlayable', 'true')
            url = '%s?mode=%s&url=%s' % (get_argv()[0], MODES.PROVIDERPLAY,
                                         quote(detail_url, safe=''))
            return url, list_item, False

    # Movies / episodes: resolve the plex:// guid to one of the user's own
    # servers on click (with the provider stream as a fallback).
    if guid or detail_url:
        list_item.setProperty('IsPlayable', 'true')
        params = ['mode=%s' % MODES.PROVIDERPLAY]
        if guid:
            params.append('guid=%s' % quote(guid, safe=''))
        if detail_url:
            params.append('url=%s' % quote(detail_url, safe=''))
        url = '%s?%s' % (get_argv()[0], '&'.join(params))
        return url, list_item, False

    # nothing playable / resolvable
    list_item.setProperty('IsPlayable', 'false')
    return '', list_item, False


def _add_watchlist_context_menu(list_item, node, in_watchlist):
    """Add a 'Add to / Remove from Watchlist' context menu entry.

    Plex only allows movies and shows on the Watchlist.
    """
    if (node.get('type') or '').lower() not in ('movie', 'show'):
        return

    # The action uses the global metadata id (last segment of the plex:// guid).
    guid = node.get('guid') or ''
    rating_key = guid.rsplit('/', 1)[-1] if guid else node.get('ratingKey')
    if not rating_key:
        return

    watchlisted = in_watchlist or node.get('watchlistedAt') is not None
    if watchlisted:
        label = i18n_or('Remove from Watchlist', 'Von Merkliste entfernen')
        command = COMMANDS.REMOVE_WATCHLIST
    else:
        label = i18n_or('Add to Watchlist', 'Zur Merkliste hinzufügen')
        command = COMMANDS.ADD_WATCHLIST

    action = 'RunScript(%s, %s, %s)' % (CONFIG['id'], command, rating_key)
    list_item.addContextMenuItems([(label, action)])


def _info_labels(title, node_type, node):
    info = {'title': title}

    mediatype = _MEDIATYPES.get(node_type)
    if mediatype:
        info['mediatype'] = mediatype

    plot = node.get('summary') or node.get('tagline')
    if plot:
        info['plot'] = plot

    if node.get('tagline'):
        info['tagline'] = node.get('tagline')
    if node.get('studio'):
        info['studio'] = node.get('studio')
    if node.get('contentRating'):
        info['mpaa'] = node.get('contentRating')
    if node.get('originallyAvailableAt'):
        info['premiered'] = node.get('originallyAvailableAt')

    if node.get('grandparentTitle'):
        info['tvshowtitle'] = node.get('grandparentTitle')

    _set_int(info, 'year', node.get('year'))
    _set_int(info, 'duration', node.get('duration'), divisor=1000)
    _set_int(info, 'season', node.get('parentIndex'))
    _set_int(info, 'episode', node.get('index'))
    _set_float(info, 'rating', node.get('rating') or node.get('audienceRating'))

    genres = [genre.get('tag') for genre in node.findall('Genre') if genre.get('tag')]
    if genres:
        info['genre'] = genres

    return info


def _set_int(info, key, value, divisor=1):
    if value is None:
        return
    try:
        info[key] = int(float(value)) // divisor if divisor != 1 else int(value)
    except (TypeError, ValueError):
        pass


def _set_float(info, key, value):
    if value is None:
        return
    try:
        info[key] = float(value)
    except (TypeError, ValueError):
        pass


def _drill_url(base, node):
    key = node.get('key') or node.get('hubKey') or ''
    if not key:
        return None
    if key.startswith('http'):
        return key
    if not key.startswith('/'):
        key = '/' + key
    return base + key


def _direct_stream_url(base, token, node):
    """Build a directly playable stream URL from an inline Media/Part, if any."""
    media = node.find('Media')
    if media is None:
        return None
    part = media.find('Part')
    if part is None:
        return None

    key = part.get('key')
    if not key:
        return None

    url = key if key.startswith('http') else base + key
    if token:
        sep = '&' if '?' in url else '?'
        url = '%s%sX-Plex-Token=%s' % (url, sep, token)
    return url


def _image_url(base, token, value):
    if not value:
        return ''
    if value.startswith('http'):
        return value
    url = base + value
    if token:
        sep = '&' if '?' in url else '?'
        url = '%s%sX-Plex-Token=%s' % (url, sep, token)
    return url


def _art(base, token, node):
    art = {}
    thumb = node.get('thumb') or node.get('grandparentThumb') or node.get('parentThumb')
    if thumb:
        thumb_url = _image_url(base, token, thumb)
        art['thumb'] = thumb_url
        art['poster'] = thumb_url
    fanart = node.get('art')
    if fanart:
        art['fanart'] = _image_url(base, token, fanart)
    return art
