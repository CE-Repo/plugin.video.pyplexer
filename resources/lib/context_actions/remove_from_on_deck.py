# -*- coding: utf-8 -*-

"""Remove the focused PyPlexer item from the Continue Watching hub."""

import re
import sys
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import xbmc  # pylint: disable=import-error
import xbmcaddon  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error


ADDON_ID = 'plugin.video.pyplexer'


def _notify_unidentified():
    addon = xbmcaddon.Addon(ADDON_ID)
    message = addon.getLocalizedString(30835) or 'Could not identify this title'
    xbmcgui.Dialog().notification(heading=addon.getAddonInfo('name'),
                                  message=message,
                                  icon=addon.getAddonInfo('icon'))


def _target(list_item):
    server_url = list_item.getProperty('PyPlexer.ServerUrl')
    media_id = list_item.getProperty('PyPlexer.MediaId')
    if server_url and media_id:
        return server_url, media_id

    plugin_url = xbmc.getInfoLabel('ListItem.FileNameAndPath')
    params = parse_qs(urlsplit(plugin_url or '').query)
    server_url = params.get('url', [''])[0]
    match = re.search(r'/metadata/(?P<metadata_id>[0-9]+)', server_url)
    if server_url and match is not None:
        return server_url, match.group('metadata_id')
    return '', ''


def run():
    # sys.listitem is injected by Kodi for kodi.context.item scripts.
    try:
        list_item = sys.listitem  # pylint: disable=no-member
    except (AttributeError, RuntimeError):
        _notify_unidentified()
        return

    server_url, media_id = _target(list_item)
    if not server_url or not media_id:
        _notify_unidentified()
        return

    xbmc.executebuiltin('RunScript(%s,remove_on_deck,%s,%s)' %
                        (ADDON_ID, server_url, media_id))


if __name__ == '__main__':
    run()
