# -*- coding: utf-8 -*-

import threading

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from artwork.fanart_tv import artwork_queue_pending
from artwork.fanart_tv import process_artwork_queue
from companion.client import get_client
from companion.receiver import CompanionReceiverThread
from companion.receiver import shutdown
from core.constants import CONFIG
from core.kodi_monitor import Monitor
from core.logger import Logger
from core.settings import AddonSettings
from playback.player import CallbackPlayer

LOG = Logger('service')


def _run_artwork_queue(stop_event):
    """Warm external artwork without delaying Kodi directory listings."""
    while not stop_event.is_set():
        try:
            completed = process_artwork_queue(AddonSettings())
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('Artwork background queue failed: %s' % error)
            completed = 0
        if (completed and not artwork_queue_pending() and
                xbmc.getInfoLabel('Container.PluginName') == CONFIG['id']):
            xbmc.executebuiltin('Container.Refresh')
        stop_event.wait(0.1 if completed else 2.0)


def run():
    settings = AddonSettings()

    sleep_time = 10

    LOG.debug('Service initialization...')

    window = xbmcgui.Window(10000)
    player = CallbackPlayer(window=window, settings=settings)
    monitor = Monitor(settings)

    companion_thread = None
    artwork_stop = threading.Event()
    artwork_thread = threading.Thread(
        target=_run_artwork_queue, args=(artwork_stop,),
        name='PyPlexerArtworkQueue')
    artwork_thread.daemon = True
    artwork_thread.start()

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
    artwork_stop.set()
    artwork_thread.join(timeout=1.0)
    player.cleanup_threads(only_ended=False)  # clean up any/all playback monitoring threads
