# -*- coding: utf-8 -*-

from core.constants import COMBINED_SECTIONS
from core.constants import MODES
from core.context import GUIItem
from gui.builders.common import get_fanart_image
from gui.builders.common import get_thumb_image
from gui.list_item import create_gui_item


def create_artist_item(context, item):
    info_labels = {
        'artist': item.data.get('title', '')
    }

    info_labels['title'] = info_labels['artist']

    prefix_server = (context.params.get('mode') in COMBINED_SECTIONS and
                     context.settings.prefix_server_in_combined())

    if prefix_server:
        info_labels['title'] = '%s: %s' % (item.server.get_name(), info_labels['title'])

    extra_data = {
        'type': 'Music',
        'thumb': get_thumb_image(context, item.server, item.data),
        'fanart_image': get_fanart_image(context, item.server, item.data),
        'ratingKey': item.data.get('title', ''),
        'key': item.data.get('key', ''),
        'mode': MODES.ALBUMS,
        'plot': item.data.get('summary', ''),
        'mediatype': 'artist'
    }

    url = item.server.join_url(item.server.get_url_location(), extra_data['key'])

    gui_item = GUIItem(url, info_labels, extra_data)
    return create_gui_item(context, gui_item)
