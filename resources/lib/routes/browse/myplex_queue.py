# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error

from core.constants import CONFIG
from core.strings import i18n
from plex.network import Plex
from processing.plex_plugins import process_plex_plugins


def run(context):
    context.plex_network = Plex(context.settings, load=True)
    if not context.plex_network.is_myplex_signedin():
        xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                      message=i18n('myPlex not configured'),
                                      icon=CONFIG['icon'])
    else:
        tree = context.plex_network.get_myplex_queue()
        process_plex_plugins(context, 'https://plex.tv/playlists/queue/all', tree)
