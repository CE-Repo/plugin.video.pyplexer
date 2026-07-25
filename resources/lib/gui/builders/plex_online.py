# -*- coding: utf-8 -*-

from core.constants import MODES
from core.context import GUIItem
from core.strings import i18n
from gui.builders.common import get_link_url
from gui.list_item import create_gui_item


def create_plex_online_item(context, item):
    if not item.data.get('title', item.data.get('name')):
        return None

    info_labels = {
        'title': item.data.get('title', item.data.get('name', i18n('Unknown')))
    }
    extra_data = {
        'type': 'Video',
        'installed': int(item.data.get('installed', 2)),
        'key': item.data.get('key', ''),
        'mode': MODES.CHANNELINSTALL
    }

    if extra_data['installed'] == 1:
        info_labels['title'] = info_labels['title'] + ' (%s)' % i18n('installed')

    elif extra_data['installed'] == 2:
        extra_data['mode'] = MODES.PLEXONLINE

    extra_data['parameters'] = {
        'name': info_labels['title']
    }

    item_url = get_link_url(item.server, item.url, item.data)

    gui_item = GUIItem(item_url, info_labels, extra_data)
    return create_gui_item(context, gui_item)
