# -*- coding: utf-8 -*-

from core.constants import MODES
from core.context import GUIItem
from core.strings import i18n
from gui.builders.common import get_banner_image
from gui.builders.common import get_clearlogo_image
from gui.builders.common import get_fanart_image
from gui.builders.common import get_thumb_image
from gui.context_menu import ContextMenu
from gui.list_item import create_gui_item


def create_season_item(context, item, library=False):
    # Create the basic data structures to pass up
    info_labels = {
        'title': item.data.get('title', i18n('Unknown')),
        'tvshowtitle': item.data.get('parentTitle', i18n('Unknown')),
        'sorttitle': item.data.get('titleSort',
                                   item.data.get('title', i18n('Unknown'))),
        'studio': [item.data.get('studio', '')],
        'plot': item.tree.get('summary', ''),
        'season': item.data.get('index', 0),
        'episode': int(item.data.get('leafCount', 0)),
        'mpaa': item.data.get('contentRating', ''),
        'aired': item.data.get('originallyAvailableAt', ''),
        'mediatype': 'season'
    }

    if item.data.get('sorttitle'):
        info_labels['sorttitle'] = item.data.get('sorttitle')

    _watched = int(item.data.get('viewedLeafCount', 0))

    extra_data = {
        'type': 'video',
        'source': 'tvseasons',
        'TotalEpisodes': info_labels['episode'],
        'WatchedEpisodes': _watched,
        'UnWatchedEpisodes': info_labels['episode'] - _watched,
        'thumb': get_thumb_image(context, item.server, item.data),
        'fanart_image': get_fanart_image(context, item.server, item.data),
        'clearlogo': get_clearlogo_image(context, item.server, item.data),
        'banner': get_banner_image(context, item.server, item.tree),
        'key': item.data.get('key', ''),
        'ratingKey': str(item.data.get('ratingKey', 0)),
        'mode': MODES.TVEPISODES
    }

    if extra_data['fanart_image'] == '':
        extra_data['fanart_image'] = get_fanart_image(context, item.server, item.tree)

    # Set up overlays for watched and unwatched episodes
    if extra_data['WatchedEpisodes'] == 0:
        info_labels['playcount'] = 0
    elif extra_data['UnWatchedEpisodes'] == 0:
        info_labels['playcount'] = 1
    else:
        extra_data['partialTV'] = 1

    item_url = item.server.join_url(item.server.get_url_location(), extra_data['key'])

    context_menu = None
    if not context.settings.skip_context_menus():
        context_menu = ContextMenu(context, item.server, item_url, item.data).menu

    if library:
        extra_data['path_mode'] = MODES.TXT_TVSHOWS_LIBRARY

    # Build the screen directory listing
    gui_item = GUIItem(item_url, info_labels, extra_data, context_menu)
    return create_gui_item(context, gui_item)
