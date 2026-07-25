# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.constants import MODES
from core.context import GUIItem
from core.strings import i18n
from core.utils import get_xml
from gui.builders.common import get_link_url
from gui.list_item import create_gui_item
from plex.network import Plex


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    server = context.plex_network.get_server_from_url(url)

    tree = get_xml(context, url)
    if tree is None:
        return

    items = []
    append_item = items.append
    directories = tree.iter('Directory')

    for channels in directories:

        if channels.get('local', '') == '0' or channels.get('size', '0') == '0':
            continue

        extra_data = {}

        details = {
            'title': channels.get('title', i18n('Unknown'))
        }

        suffix = channels.get('key').split('/')[1]

        if channels.get('unique', '') == '0':
            details['title'] = '%s (%s)' % (details['title'], suffix)

        # Alter data sent into get_link_url, as channels use path rather than key
        path_data = {
            'key': channels.get('key'),
            'identifier': channels.get('key')
        }
        p_url = get_link_url(server, url, path_data)

        extra_data['mode'] = MODES.GETCONTENT
        if suffix == 'photos':
            extra_data['mode'] = MODES.PHOTOS
        elif suffix == 'video':
            extra_data['mode'] = MODES.PLEXPLUGINS
        elif suffix == 'music':
            extra_data['mode'] = MODES.MUSIC

        gui_item = GUIItem(p_url, details, extra_data)
        append_item(create_gui_item(context, gui_item))

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
