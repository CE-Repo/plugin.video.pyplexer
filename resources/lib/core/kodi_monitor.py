# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error

from core.constants import CONFIG
from core.logger import Logger


class Monitor(xbmc.Monitor):
    LOG = Logger('Monitor')

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def __str__(self):
        return '%s(%s)' % (self.__class__.__name__, CONFIG['id'])

    def onNotification(self, sender, method, data):  # pylint: disable=invalid-name
        """
        Handle any notifications directed to this add-on
        """
        if CONFIG['id'] not in method:
            return

        self.LOG.debug('Notification from %s: %s -> %s' % (sender, method, data))
