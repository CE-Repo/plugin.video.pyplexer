# -*- coding: utf-8 -*-

from core.constants import MODES
from core.context import GUIItem
from core.strings import directory_item_translate
from core.strings import i18n
from gui.builders.common import get_link_url
from gui.list_item import create_gui_item


def create_directory_item(context, item):
    title = item.data.get('title', i18n('Unknown'))
    title = directory_item_translate(title, item.tree.get('thumb'))

    info_labels = {
        'title': title
    }

    if '/collection' in item.url:
        info_labels['mediatype'] = 'set'

    extra_data = {
        'mode': MODES.GETCONTENT,
        'type': 'Folder'
    }

    item_url = '%s' % (get_link_url(item.server, item.url, item.data))

    gui_item = GUIItem(item_url, info_labels, extra_data)
    return create_gui_item(context, gui_item)
