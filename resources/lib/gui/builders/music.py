# -*- coding: utf-8 -*-

from core.constants import MODES
from core.context import GUIItem
from core.logger import Logger
from core.strings import i18n
from gui.builders.common import get_fanart_image
from gui.builders.common import get_link_url
from gui.builders.common import get_thumb_image
from gui.list_item import create_gui_item

LOG = Logger()


def create_music_item(context, item):
    info_labels = {
        'genre': item.data.get('genre', ''),
        'artist': item.data.get('artist', ''),
        'year': int(item.data.get('year', 0)),
        'album': item.data.get('album', ''),
        'tracknumber': int(item.data.get('index', 0)),
        'title': i18n('Unknown')
    }

    extra_data = {
        'type': 'Music',
        'thumb': get_thumb_image(context, item.server, item.data),
        'fanart_image': get_fanart_image(context, item.server, item.data)
    }

    if extra_data['fanart_image'] == '':
        extra_data['fanart_image'] = get_fanart_image(context, item.server, item.tree)

    item_url = get_link_url(item.server, item.url, item.data)

    if item.data.tag == 'Track':
        LOG.debug('Track Tag')
        info_labels['mediatype'] = 'song'
        info_labels['title'] = item.data.get('track',
                                             item.data.get('title', i18n('Unknown')))
        info_labels['duration'] = int(int(item.data.get('total_time', 0)) / 1000)

        extra_data['mode'] = MODES.BASICPLAY

        gui_item = GUIItem(item_url, info_labels, extra_data)
        gui_item.is_folder = False
        return create_gui_item(context, gui_item)

    info_labels['mediatype'] = 'artist'

    if item.data.tag == 'Artist':
        LOG.debug('Artist Tag')
        info_labels['mediatype'] = 'artist'
        info_labels['title'] = item.data.get('artist', i18n('Unknown'))

    elif item.data.tag == 'Album':
        LOG.debug('Album Tag')
        info_labels['mediatype'] = 'album'
        info_labels['title'] = item.data.get('album', i18n('Unknown'))

    elif item.data.tag == 'Genre':
        info_labels['title'] = item.data.get('genre', i18n('Unknown'))

    else:
        LOG.debug('Generic Tag: %s' % item.data.tag)
        info_labels['title'] = item.data.get('title', i18n('Unknown'))

    extra_data['mode'] = MODES.MUSIC

    gui_item = GUIItem(item_url, info_labels, extra_data)
    return create_gui_item(context, gui_item)
