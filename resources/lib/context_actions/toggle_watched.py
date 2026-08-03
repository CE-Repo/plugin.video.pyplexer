# -*- coding: utf-8 -*-

"""Mark the focused PyPlexer item watched or unwatched."""

import json
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


def _target(list_item, info_tag):
    server_url = list_item.getProperty('PyPlexer.ServerUrl')
    media_id = list_item.getProperty('PyPlexer.MediaId')
    if server_url and media_id:
        return server_url, media_id

    try:
        plugin_url = info_tag.getFilenameAndPath()
    except (AttributeError, RuntimeError):
        plugin_url = xbmc.getInfoLabel('ListItem.FileNameAndPath')

    if not plugin_url:
        plugin_url = xbmc.getInfoLabel('ListItem.FileNameAndPath')

    params = parse_qs(urlsplit(plugin_url or '').query)
    server_url = params.get('url', [''])[0]
    match = re.search(r'/metadata/(?P<metadata_id>[0-9]+)', server_url)
    if server_url and match is not None:
        return server_url, match.group('metadata_id')
    return '', ''


def _update_kodi_library(info_tag, watched):
    database_id = info_tag.getDbId()
    media_type = info_tag.getMediaType()
    methods = {
        'movie': 'VideoLibrary.SetMovieDetails',
        'tvshow': 'VideoLibrary.SetTVShowDetails',
        'episode': 'VideoLibrary.SetEpisodeDetails',
    }
    method = methods.get(media_type)
    if not database_id or method is None:
        return

    query = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': method,
        'params': {
            '%sid' % media_type: database_id,
            'playcount': 1 if watched else 0,
            'resume': {'position': 0.0},
        },
    }
    xbmc.executeJSONRPC(json.dumps(query))


def run(watched):
    try:
        list_item = sys.listitem  # pylint: disable=no-member
        info_tag = list_item.getVideoInfoTag()
    except (AttributeError, RuntimeError):
        _notify_unidentified()
        return

    server_url, media_id = _target(list_item, info_tag)
    action = 'watch' if watched else 'unwatch'
    if server_url and media_id:
        xbmc.executebuiltin('RunScript(%s,watch,%s,%s,%s)' %
                            (ADDON_ID, server_url, media_id, action))
    else:
        _notify_unidentified()
        return

    _update_kodi_library(info_tag, watched)
