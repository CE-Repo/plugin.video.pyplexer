# -*- coding: utf-8 -*-

import hashlib

from core.constants import COMBINED_SECTIONS
from core.constants import MODES
from core.context import GUIItem
from core.logger import Logger
from core.strings import i18n
from gui.builders.common import get_banner_image
from gui.builders.common import get_clearlogo_image
from gui.builders.common import get_fanart_image
from gui.builders.common import get_metadata
from gui.builders.common import get_thumb_image
from gui.context_menu import ContextMenu
from gui.list_item import create_gui_item

LOG = Logger()


def create_show_item(context, item, library=False):
    metadata = get_metadata(context, item.data)

    # Create the basic data structures to pass up
    info_labels = {
        'title': item.data.get('title', i18n('Unknown')),
        'sorttitle': item.data.get('titleSort',
                                   item.data.get('title', i18n('Unknown'))),
        'tvshowtitle': item.data.get('title', i18n('Unknown')),
        'studio': [item.data.get('studio', '')],
        'plot': item.data.get('summary', ''),
        'season': 0,
        'episode': int(item.data.get('leafCount', 0)),
        'mpaa': item.data.get('contentRating', ''),
        'rating': float(item.data.get('rating', 0)),
        'aired': item.data.get('originallyAvailableAt', ''),
        'cast': metadata['cast'],
        'genre': metadata['genre'],
        'mediatype': 'tvshow'
    }

    prefix_server = (context.params.get('mode') in COMBINED_SECTIONS and
                     context.settings.prefix_server_in_combined())

    if prefix_server:
        info_labels['title'] = '%s: %s' % (item.server.get_name(), info_labels['title'])

    _watched = int(item.data.get('viewedLeafCount', 0))

    extra_data = {
        'type': 'video',
        'source': 'tvshows',
        'UnWatchedEpisodes': int(info_labels['episode']) - _watched,
        'WatchedEpisodes': _watched,
        'TotalEpisodes': info_labels['episode'],
        'thumb': get_thumb_image(context, item.server, item.data),
        'fanart_image': get_fanart_image(context, item.server, item.data),
        'clearlogo': get_clearlogo_image(context, item.server, item.data),
        'banner': get_banner_image(context, item.server, item.data),
        'key': item.data.get('key', ''),
        'ratingKey': str(item.data.get('ratingKey', 0)),
        'guid': item.data.get('guid', '')
    }

    # Set up overlays for watched and unwatched episodes
    if extra_data['WatchedEpisodes'] == 0:
        info_labels['playcount'] = 0
    elif extra_data['UnWatchedEpisodes'] == 0:
        info_labels['playcount'] = 1
    else:
        extra_data['partialTV'] = 1

    # Create URL based on whether we are going to flatten the season view
    if context.settings.flatten_seasons() == '2':
        LOG.debug('Flattening all shows')
        extra_data['mode'] = MODES.TVEPISODES
        item_url = item.server.join_url(item.server.get_url_location(),
                                        extra_data['key'].replace('children', 'allLeaves'))
    else:
        extra_data['mode'] = MODES.TVSEASONS
        item_url = item.server.join_url(item.server.get_url_location(), extra_data['key'])

    context_menu = None
    if not context.settings.skip_context_menus():
        context_menu = ContextMenu(context, item.server, item.url, extra_data).menu

    if library:
        extra_data['hash'] = _md5_hash(item.data)
        extra_data['path_mode'] = MODES.TXT_TVSHOWS_LIBRARY

    gui_item = GUIItem(item_url, info_labels, extra_data, context_menu)
    return create_gui_item(context, gui_item)


def _md5_hash(show):
    show_hash = hashlib.md5()
    show_hash.update(show.get('addedAt', u'').encode('utf-8'))
    show_hash.update(show.get('updatedAt', u'').encode('utf-8'))
    return show_hash.hexdigest().upper()
