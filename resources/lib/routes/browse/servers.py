# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.constants import MODES
from core.context import GUIItem
from core.logger import Logger
from gui.list_item import create_gui_item
from plex.network import Plex
from processing.music import process_music
from processing.photos import process_photos
from processing.plex_online import process_plex_online
from processing.plex_plugins import process_plex_plugins

LOG = Logger()


def run(context, url):
    context.plex_network = Plex(context.settings, load=True)
    content_type = url.split('/')[2]
    LOG.debug('Displaying entries for %s' % content_type)
    servers = context.plex_network.get_server_list()
    servers_list = len(servers)

    items = []
    append_item = items.append
    # For each of the servers we have identified
    for media_server in servers:

        if media_server.is_secondary():
            continue

        details = {
            'title': media_server.get_name()
        }
        extra_data = {}
        url = None

        if content_type == 'video':
            extra_data['mode'] = MODES.PLEXPLUGINS
            url = media_server.join_url(media_server.get_url_location(), 'video')
            if servers_list == 1:
                process_plex_plugins(context, url)
                return

        elif content_type == 'online':
            extra_data['mode'] = MODES.PLEXONLINE
            url = media_server.join_url(media_server.get_url_location(), 'system/plexonline')
            if servers_list == 1:
                process_plex_online(context, url)
                return

        elif content_type == 'music':
            extra_data['mode'] = MODES.MUSIC
            url = media_server.join_url(media_server.get_url_location(), 'music')
            if servers_list == 1:
                process_music(context, url)
                return

        elif content_type == 'photo':
            extra_data['mode'] = MODES.PHOTOS
            url = media_server.join_url(media_server.get_url_location(), 'photos')
            if servers_list == 1:
                process_photos(context, url)
                return

        if url:
            gui_item = GUIItem(url, details, extra_data)
            append_item(create_gui_item(context, gui_item))

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())
