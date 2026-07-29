# -*- coding: utf-8 -*-

from xbmc import Player  # pylint: disable=import-error
from xbmcgui import WindowXMLDialog  # pylint: disable=import-error

from core.logger import Logger


class SkipIntroDialog(WindowXMLDialog):
    LOG = Logger('SkipIntroDialog')

    BUTTON_ID = 3002
    PROGRESS_ID = 3011
    PROGRESS_WIDTH = 500  # keep in sync with skip_intro.xml

    def __init__(self, *args, **kwargs):
        self.intro_start = kwargs.pop('intro_start', None)
        self.intro_end = kwargs.pop('intro_end', None)

        self._showing = False
        self._player = None
        self._on_hold = False

        self.LOG.debug('Dialog initialized, Intro runs from %s to %s' %
                       (self._log_time(self.intro_start), self._log_time(self.intro_end)))
        WindowXMLDialog.__init__(self, *args, **kwargs)

    def show(self):
        if not self.intro_end:
            self.close()
            return

        if not self.on_hold and not self.showing:
            self.LOG.debug('Showing dialog')
            self.showing = True
            WindowXMLDialog.show(self)

    def close(self):
        if self.showing:
            self.showing = False
            self.LOG.debug('Closing dialog')
            WindowXMLDialog.close(self)

    def update_progress(self, current_time):
        """Shrink the bar underneath the button as the intro plays out, so the
        remaining window for skipping is visible at a glance."""
        if not self.showing:
            return

        width = int(round(self.PROGRESS_WIDTH * self._remaining(current_time)))

        try:
            self.getControl(self.PROGRESS_ID).setWidth(width)
        except (RuntimeError, TypeError):  # control missing, or window already gone
            pass

    def _remaining(self, current_time):
        try:
            start = int(self.intro_start or 0)
            end = int(self.intro_end)
            current = int(current_time)
        except (TypeError, ValueError):
            return 1.0

        length = end - start
        if length <= 0:
            return 1.0

        return max(0.0, min(1.0, (end - current) / float(length)))

    def onClick(self, control_id):  # pylint: disable=invalid-name
        if self.intro_end and control_id == self.BUTTON_ID:
            if self.player.isPlaying():
                self.on_hold = True
                self.player.seekTime(self.intro_end // 1000)
                self.close()

    def onAction(self, action):  # pylint: disable=invalid-name
        close_actions = [10, 13, 92]
        # 10 = previousmenu, 13 = stop, 92 = back
        if action in close_actions:
            self.on_hold = True
            self.close()

    @property
    def player(self):
        if self._player is None:
            self._player = Player()
        return self._player

    @property
    def showing(self):
        return self._showing

    @showing.setter
    def showing(self, value):
        self._showing = bool(value)

    @property
    def on_hold(self):
        return self._on_hold

    @on_hold.setter
    def on_hold(self, value):
        self._on_hold = bool(value)

    @staticmethod
    def _log_time(mil):
        if not isinstance(mil, int):
            return 'undefined'
        secs = (mil // 1000) % 60
        mins = (mil // (1000 * 60)) % 60
        return '%d:%02d' % (int(mins), int(secs))
