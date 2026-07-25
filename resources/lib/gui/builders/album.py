# -*- coding: utf-8 -*-

from core.constants import COMBINED_SECTIONS
from core.constants import MODES
from core.context import GUIItem
from gui.builders.common import get_fanart_image
from gui.builders.common import get_thumb_image
from gui.list_item import create_gui_item


def create_album_item(context, item):
    info_labels = {
        'album': item.data.get('title', ''),
        'year': int(item.data.get('year', 0)),
        'artist': item.tree.get('parentTitle', item.data.get('parentTitle', '')),
        'mediatype': 'album'
    }

    info_labels['title'] = info_labels['album']
    if 'recentlyAdded' in item.url:
        info_labels['title'] = '%s - %s' % (info_labels['artist'], info_labels['title'])

    prefix_server = (context.params.get('mode') in COMBINED_SECTIONS and
                     context.settings.prefix_server_in_combined())

    if prefix_server:
        info_labels['title'] = '%s: %s' % (item.server.get_name(), info_labels['title'])

    extra_data = {
        'type': 'Music',
        'thumb': get_thumb_image(context, item.server, item.data),
        'fanart_image': get_fanart_image(context, item.server, item.data),
        'key': item.data.get('key', ''),
        'mode': MODES.TRACKS,
        'plot': item.data.get('summary', '')
    }

    if extra_data['fanart_image'] == '':
        extra_data['fanart_image'] = get_fanart_image(context, item.server, item.tree)

    url = item.server.join_url(item.server.get_url_location(), extra_data['key'])

    gui_item = GUIItem(url, info_labels, extra_data)
    return create_gui_item(context, gui_item)
