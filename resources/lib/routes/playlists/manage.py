# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from core.logger import Logger
from core.utils import wait_for_busy_dialog
from gui.dialogs.playlist_picker import pyplexer_playlist
from plex.network import Plex

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)
    play = pyplexer_playlist(context) and wait_for_busy_dialog()
    if play:
        xbmc.Player().play(item=xbmc.PlayList(xbmc.PLAYLIST_VIDEO), startpos=0)
