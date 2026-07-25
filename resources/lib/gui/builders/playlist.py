# -*- coding: utf-8 -*-

from core.constants import MODES
from core.context import GUIItem
from core.strings import i18n
from gui.builders.common import get_link_url
from gui.context_menu import ContextMenu
from gui.list_item import create_gui_item


def create_playlist_item(context, item, listing=True):
    info_labels = {
        'title': item.data.get('title', i18n('Unknown')),
        'duration': int(item.data.get('duration', 0)) / 1000
    }

    extra_data = {
        'playlist': True,
        'ratingKey': item.data.get('ratingKey'),
        'type': item.data.get('playlistType', ''),
        'mode': MODES.GETCONTENT
    }

    if extra_data['type'] == 'video':
        extra_data['mode'] = MODES.MOVIES
    elif extra_data['type'] == 'audio':
        extra_data['mode'] = MODES.TRACKS
    elif extra_data['type'] == 'photo':
        extra_data['mode'] = MODES.PHOTOS

    item_url = get_link_url(item.server, item.url, item.data)

    context_menu = None
    if not context.settings.skip_context_menus():
        context_menu = ContextMenu(context, item.server, item_url, extra_data).menu

    if listing:
        gui_item = GUIItem(item_url, info_labels, extra_data, context_menu)
        return create_gui_item(context, gui_item)

    return item.url, info_labels
