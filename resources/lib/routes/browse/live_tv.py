# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n
from gui.builders.live_tv import create_live_tv_item
from plex.live_tv import dvr_channels
from plex.live_tv import plex_channels
from plex.network import Plex
from processing.pagination import paginate_local_items

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)
    xbmcplugin.setContent(get_handle(), 'files')

    channels = []
    for server in context.plex_network.get_server_list():
        if server.is_offline() or server.is_secondary():
            continue
        channels += dvr_channels(server)

    channels += plex_channels(context.plex_network)

    LOG.debug('Live TV: %s channel(s) in total' % len(channels))

    if not channels:
        xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                      message=i18n('No Live TV channels found'),
                                      icon=CONFIG['icon'])

    items = [item for item in
             (create_live_tv_item(context, channel) for channel in channels)
             if item]
    items = paginate_local_items(context, items)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=False)
