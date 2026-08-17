# -*- coding: utf-8 -*-

from core.constants import MODES
from core.context import GUIItem
from gui.list_item import create_gui_item


def create_live_tv_item(context, channel):
    """One channel of a DVR lineup or of Plex' own free lineup."""
    title = channel.get('title')
    if not title:
        return None

    number = channel.get('number')
    if number:
        title = '%s %s' % (number, title)

    info_labels = {
        'title': title
    }

    if channel.get('summary'):
        info_labels['plot'] = channel['summary']

    extra_data = {
        'type': 'Video',
        'mode': MODES.LIVETVPLAY,
        'thumb': channel.get('logo', ''),
        # a channel runs on without an end, so there is nothing to resume into
        'duration': 0,
        'resume': 0,
        # everything the play route needs to tune this channel again
        'parameters': {
            'live_source': channel.get('source', ''),
            'live_key': channel.get('key', ''),
            'live_dvr': channel.get('dvr', ''),
            'live_base': channel.get('base', ''),
            'live_stream': channel.get('stream', ''),
            'server_uuid': channel.get('server_uuid', ''),
        }
    }

    gui_item = GUIItem('http://livetv/%s' % channel.get('source', ''),
                       info_labels, extra_data)
    gui_item.is_folder = False
    return create_gui_item(context, gui_item)
