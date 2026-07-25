# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error

from companion.client import get_client
from companion.receiver import CompanionReceiverThread
from companion.receiver import shutdown
from core.kodi_monitor import Monitor
from core.logger import Logger
from core.settings import AddonSettings
from playback.player import CallbackPlayer

LOG = Logger('service')


def run():
    settings = AddonSettings()

    sleep_time = 10

    LOG.debug('Service initialization...')

    window = xbmcgui.Window(10000)
    player = CallbackPlayer(window=window, settings=settings)
    monitor = Monitor(settings)

    companion_thread = None

    while not monitor.abortRequested():

        if not companion_thread and settings.use_companion():
            _fresh_settings = AddonSettings()
            companion_thread = CompanionReceiverThread(get_client(_fresh_settings),
                                                                 _fresh_settings)
            del _fresh_settings
        elif companion_thread and not settings.use_companion():
            shutdown(companion_thread)
            companion_thread = None

        if monitor.waitForAbort(sleep_time):
            break

    shutdown(companion_thread)
    player.cleanup_threads(only_ended=False)  # clean up any/all playback monitoring threads
