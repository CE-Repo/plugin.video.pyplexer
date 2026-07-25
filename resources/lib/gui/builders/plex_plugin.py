# -*- coding: utf-8 -*-

from core.constants import MODES
from core.context import GUIItem
from core.strings import i18n
from gui.builders.common import get_link_url
from gui.builders.common import get_thumb_image
from gui.list_item import create_gui_item


def create_plex_plugin_item(context, item):
    if not item.data.get('title'):
        return None

    info_labels = {
        'title': item.data.get('title')
    }

    if info_labels['title']:
        info_labels['title'] = item.data.get('name', i18n('Unknown'))

    if item.data.get('summary'):
        info_labels['plot'] = item.data.get('summary')

    extra_data = {
        'thumb': get_thumb_image(context, item.server, item.data),
        'identifier': item.tree.get('identifier', ''),
        'type': 'Video',
        'key': item.data.get('key', '')
    }

    if ((item.tree.get('identifier') != 'com.plexapp.plugins.myplex') and
            ('node.plexapp.com' in item.url)):
        extra_data['key'] = extra_data['key'].replace('node.plexapp.com:32400',
                                                      item.server.get_location())

    item_url = get_link_url(item.server, item.url, extra_data)

    if item.data.tag in ['Directory', 'Podcast']:
        gui_item = GUIItem(item_url, info_labels, extra_data)
        return get_directory_item(context, item.data, gui_item)

    if item.data.tag == 'Setting':
        gui_item = GUIItem(item.url, info_labels, extra_data)
        return get_setting_item(context, item.data, gui_item)

    if item.data.tag == 'Video':
        gui_item = GUIItem(item_url, info_labels, extra_data)
        return get_video_item(context, item.data, gui_item)

    return None


def get_directory_item(context, data, item):
    # Navigation folders use the skin's native default icon
    item.extra['thumb'] = ''
    item.extra['mode'] = MODES.PLEXPLUGINS
    if data.get('search') == '1':
        item.extra['mode'] = MODES.CHANNELSEARCH
        item.extra['parameters'] = {
            'prompt': data.get('prompt', i18n('Enter search term'))
        }

    gui_item = GUIItem(item.url, item.info_labels, item.extra)
    return create_gui_item(context, gui_item)


def get_setting_item(context, data, item):
    value = data.get('value')
    if data.get('option') == 'hidden':
        value = '********'
    elif data.get('type') == 'text':
        value = data.get('value')
    elif data.get('type') == 'enum':
        value = data.get('values').split('|')[int(data.get('value', 0))]

    item.info_labels['title'] = '%s - [%s]' % \
                                (data.get('label', i18n('Unknown')), value)
    item.extra['mode'] = MODES.CHANNELPREFS
    item.extra['parameters'] = {
        'id': data.get('id')
    }

    gui_item = GUIItem(item.url, item.info_labels, item.extra)
    return create_gui_item(context, gui_item)


def get_video_item(context, data, item):
    item.extra['mode'] = MODES.VIDEOPLUGINPLAY

    for child in data:
        if child.tag == 'Media':
            item.extra['parameters'] = {
                'indirect': child.get('indirect', '0')
            }

    gui_item = GUIItem(item.url, item.info_labels, item.extra)
    gui_item.is_folder = False
    return create_gui_item(context, gui_item)
