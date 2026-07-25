# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from core.constants import CONFIG
from gui.dialogs.skip_intro import SkipIntroDialog


def run():
    monitor = xbmc.Monitor()
    dialog = SkipIntroDialog('skip_intro.xml',
                             CONFIG['addon'].getAddonInfo('path'),
                             'default', '720p', intro_end=1000000)
    xbmc.executebuiltin('Dialog.Close(all,true)')
    dialog.show()
    monitor.waitForAbort(0.5)
    while not monitor.abortRequested() and dialog.showing:
        if monitor.waitForAbort(0.5):
            break
    dialog.close()
