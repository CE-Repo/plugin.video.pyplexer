# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from core.constants import CONFIG
from gui.dialogs.skip_intro import SkipIntroDialog

PREVIEW_LENGTH = 60000  # ms, a full countdown cycle for the preview
TICK = 0.5


def run():
    monitor = xbmc.Monitor()
    dialog = SkipIntroDialog('skip_intro.xml',
                             CONFIG['addon'].getAddonInfo('path'),
                             'default', '720p',
                             intro_start=0, intro_end=PREVIEW_LENGTH)
    xbmc.executebuiltin('Dialog.Close(all,true)')
    dialog.show()
    monitor.waitForAbort(TICK)

    elapsed = 0
    while not monitor.abortRequested() and dialog.showing:
        # no player to follow here, so run the countdown off the clock and loop
        # it, letting the preview show the bar the same way playback does
        elapsed = (elapsed + int(TICK * 1000)) % PREVIEW_LENGTH
        dialog.update_progress(elapsed)
        if monitor.waitForAbort(TICK):
            break

    dialog.close()
