# -*- coding: utf-8 -*-

"""Open the focused PyPlexer folder in Kodi's Videos window."""

import sys

import xbmc  # pylint: disable=import-error


if __name__ == '__main__':
    # sys.listitem is injected by Kodi when running as a context menu item.
    list_item = sys.listitem  # pylint: disable=no-member
    folder_url = list_item.getProperty('PyPlexer.FolderUrl')
    if not folder_url:
        folder_url = xbmc.getInfoLabel('Container.FolderPath')

    if folder_url:
        xbmc.executebuiltin('ActivateWindow(Videos,%s,return)' % folder_url)
