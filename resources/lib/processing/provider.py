# -*- coding: utf-8 -*-

"""Render Plex account-provider content (Watchlist / Discover).

These items come from plex.tv providers (metadata/discover.provider.plex.tv) and
are NOT tied to a specific Plex Media Server, so they are shown as a browsable
listing (posters + metadata) rather than being played directly. Containers
(hubs, shows, seasons) become folders that drill deeper via MODES.PROVIDERBROWSE.
"""

import copy
from urllib.parse import quote

import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from infotagger.listitem import ListItemInfoTag  # pylint: disable=import-error

from artwork.fanart_tv import CLEARLOGO_ATTRIBUTE
from artwork.fanart_tv import THUMB_ATTRIBUTE
from artwork.fanart_tv import external_id
from artwork.fanart_tv import is_configured
from artwork.fanart_tv import prefer_artwork
from core.common import get_argv
from core.common import get_current_plugin_url
from core.common import get_handle
from core.constants import MODES
from core.logger import Logger
from core.strings import i18n
from gui.builders.common import get_media_data

LOG = Logger()

# node types / tags that are containers the user can drill into
_FOLDER_TYPES = ('show', 'season', 'artist', 'album')
_FOLDER_TAGS = ('Hub', 'Directory', 'Playlist')
_CONTENT_TAGS = ('Hub', 'Directory', 'Playlist', 'Video')

#: Items whose plot is fetched with one request; a long list is done in
#: several.  Twenty is what the provider hands out per container, so a batch of
#: that size comes back whole even where the size asked for is ignored.
SUMMARY_BATCH_SIZE = 20

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

    nodes = list(_iter_nodes(tree))
    _attach_summaries(context, base, nodes)
    prefer_artwork(context, [node for node in nodes
                             if (node.get('type') or '').lower() == 'movie'], 'movie')
    prefer_artwork(context, [node for node in nodes
                             if (node.get('type') or '').lower() == 'show'], 'show')
    watchlist_ids = (set() if in_watchlist else
                     context.plex_network.get_provider_watchlist_ids())

    items = []
    current_folder_url = get_current_plugin_url()
    for node in nodes:
        entry = _build_item(base, token, node, in_watchlist, watchlist_ids)
        if entry:
            _set_folder_property(entry, current_folder_url)
            items.append(entry)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(),
                              cacheToDisc=context.settings.cache_directory())


def _set_folder_property(entry, parent_url):
    item_url, list_item, is_folder = entry
    folder_url = item_url if is_folder else parent_url
    if folder_url:
        list_item.setProperty('PyPlexer.FolderUrl', folder_url)


def _iter_nodes(tree):
    for node in list(tree):
        if node.tag in _CONTENT_TAGS:
            yield node


def _attach_summaries(context, base, nodes):
    """Fill in plots, external ids and Plex logos provider listings omit.

    The Watchlist answers with the tagline but without the summary; the
    metadata of the items has it.  Plex takes several rating keys in one go, so
    a whole page costs a single request.  Anything that does not come back is
    simply left without a plot.
    """
    use_external_artwork = is_configured(context.settings)

    def needs_details(node):
        if not node.get('ratingKey'):
            return False
        if not node.get('summary'):
            return True
        if not use_external_artwork:
            return False
        node_type = (node.get('type') or '').lower()
        if node_type not in ('movie', 'show'):
            return False
        if not external_id(node, node_type)[1]:
            return True
        has_clearlogo = (node.get('clearLogo') or
                         any((image.get('type') or '').lower() == 'clearlogo'
                             for image in node.findall('Image')))
        return not has_clearlogo

    missing = [node for node in nodes if needs_details(node)]

    if not missing:
        return

    details = {}

    # a long Watchlist is asked for in batches rather than in one huge URL
    for offset in range(0, len(missing), SUMMARY_BATCH_SIZE):
        batch = missing[offset:offset + SUMMARY_BATCH_SIZE]
        keys = ','.join([node.get('ratingKey') for node in batch])

        tree = context.plex_network.get_provider_metadata(base, keys)
        if tree is None:
            LOG.debug('No summaries for %s item(s)' % len(batch))
            continue

        before = len(details)
        for element in tree.iter():
            rating_key = element.get('ratingKey')
            if rating_key:
                details[str(rating_key)] = element

        LOG.debug('Summary batch: asked for %s, answered with %s' %
                  (len(batch), len(details) - before))

    filled = 0
    for node in missing:
        detail = details.get(str(node.get('ratingKey')))
        if detail is None:
            continue
        if not node.get('summary') and detail.get('summary'):
            node.set('summary', detail.get('summary'))
            filled += 1
        if not node.findall('Guid'):
            for guid in detail.findall('Guid'):
                node.append(copy.copy(guid))
        if not node.get('clearLogo') and detail.get('clearLogo'):
            node.set('clearLogo', detail.get('clearLogo'))
        has_clearlogo = any((image.get('type') or '').lower() == 'clearlogo'
                            for image in node.findall('Image'))
        if not has_clearlogo:
            for image in detail.findall('Image'):
                if (image.get('type') or '').lower() == 'clearlogo':
                    node.append(copy.copy(image))
                    break

    LOG.debug('Summary filled in for %s of %s item(s)' % (filled, len(missing)))


def _build_item(base, token, node, in_watchlist=False, watchlist_ids=None):
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
        stream_info = get_media_data(dict(media.items()), media, node).get('stream_info', {})
        info_tag.add_stream_info('video', stream_info.get('video', {}))
        info_tag.add_stream_info('audio', stream_info.get('audio', {}))

    _set_watchlist_properties(list_item, node, in_watchlist, watchlist_ids)

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


def _set_watchlist_properties(list_item, node, in_watchlist, watchlist_ids=None):
    """Expose Watchlist data for the context items declared in addon.xml.

    Plex only allows movies and shows on the Watchlist.
    """
    if (node.get('type') or '').lower() not in ('movie', 'show'):
        return

    # The action uses the global metadata id (last segment of the plex:// guid).
    guid = node.get('guid') or ''
    rating_key = guid.rsplit('/', 1)[-1] if guid else node.get('ratingKey')
    if not rating_key:
        return

    watchlisted = (in_watchlist or node.get('watchlistedAt') is not None or
                   str(rating_key) in (watchlist_ids or set()))
    list_item.setProperty('PyPlexer.WatchlistRatingKey', str(rating_key))
    list_item.setProperty('PyPlexer.Watchlisted', 'true' if watchlisted else 'false')


def _info_labels(title, node_type, node):
    info = {'title': title}

    mediatype = _MEDIATYPES.get(node_type)
    if mediatype:
        info['mediatype'] = mediatype

    # the tagline is not a plot; showing it as one puts the same sentence on
    # the screen twice
    if node.get('summary'):
        info['plot'] = node.get('summary')

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
    fanart_thumb = node.get(THUMB_ATTRIBUTE)
    if fanart_thumb:
        art['landscape'] = fanart_thumb
    clearlogo = node.get(CLEARLOGO_ATTRIBUTE) or node.get('clearLogo')
    if not clearlogo:
        for image in node.findall('Image'):
            if (image.get('type') or '').lower() == 'clearlogo':
                clearlogo = image.get('url') or ''
                break
    if clearlogo:
        clearlogo_url = _image_url(base, token, clearlogo)
        art['clearlogo'] = clearlogo_url
        art['logo'] = clearlogo_url
    fanart = node.get('art')
    if fanart:
        art['fanart'] = _image_url(base, token, fanart)
    return art
