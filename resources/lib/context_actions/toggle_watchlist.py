# -*- coding: utf-8 -*-

"""Run an explicit Plex Watchlist action for the focused Kodi item."""

import re
import sys
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import xbmc  # pylint: disable=import-error
import xbmcaddon  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error


ADDON_ID = 'plugin.video.pyplexer'
COMMANDS = {
    True: 'add_external_watchlist',
    False: 'remove_external_watchlist',
}
DIRECT_COMMANDS = {
    True: 'add_watchlist',
    False: 'remove_watchlist',
}
SUPPORTED_IDS = ('tmdb', 'imdb', 'tvdb')


def _clean_id(value):
    value = str(value or '').strip()
    return value if re.fullmatch(r'[A-Za-z0-9._-]+', value) else ''


def _media_type(info_tag, params):
    try:
        value = info_tag.getMediaType()
    except (AttributeError, RuntimeError):
        value = ''

    value = (value or params.get('tmdb_type', [''])[0] or
             xbmc.getInfoLabel('ListItem.DBTYPE')).lower()
    if value == 'movie':
        return 'movie'
    if value in ('show', 'tv', 'tvshow'):
        return 'show'
    return ''


def _unique_id(list_item, info_tag, params):
    for provider in SUPPORTED_IDS:
        value = ''
        try:
            value = info_tag.getUniqueID(provider)
        except (AttributeError, RuntimeError):
            pass

        if not value:
            value = list_item.getProperty('%s_id' % provider)
        if not value:
            value = list_item.getProperty('item.%s_id' % provider)
        if not value:
            value = params.get('%s_id' % provider, [''])[0]
        if not value:
            value = xbmc.getInfoLabel('ListItem.UniqueID(%s)' % provider)

        value = _clean_id(value)
        if value:
            return '%s://%s' % (provider, value)

    return ''


def _notify_unidentified():
    addon = xbmcaddon.Addon(ADDON_ID)
    message = addon.getLocalizedString(30835) or 'Could not identify this title'
    xbmcgui.Dialog().notification(heading=addon.getAddonInfo('name'),
                                  message=message,
                                  icon=addon.getAddonInfo('icon'))


def run(add):
    # sys.listitem is injected by Kodi for kodi.context.item scripts.
    try:
        list_item = sys.listitem  # pylint: disable=no-member
        info_tag = list_item.getVideoInfoTag()
    except (AttributeError, RuntimeError):
        _notify_unidentified()
        return

    # PyPlexer listings already know the provider rating key. Using it avoids
    # resolving an external TMDb/IMDb/TVDb id and lets the global context item
    # replace the old top-level addContextMenuItems() action.
    rating_key = _clean_id(list_item.getProperty('PyPlexer.WatchlistRatingKey'))
    if rating_key:
        xbmc.executebuiltin('RunScript(%s,%s,%s)' %
                            (ADDON_ID, DIRECT_COMMANDS[bool(add)], rating_key))
        return

    try:
        path = info_tag.getFilenameAndPath()
    except (AttributeError, RuntimeError):
        path = xbmc.getInfoLabel('ListItem.FileNameAndPath')

    params = parse_qs(urlsplit(path or '').query)
    media_type = _media_type(info_tag, params)
    external_guid = _unique_id(list_item, info_tag, params)

    if not media_type or not external_guid:
        _notify_unidentified()
        return

    xbmc.executebuiltin('RunScript(%s,%s,%s,%s)' %
                        (ADDON_ID, COMMANDS[bool(add)], media_type, external_guid))
