# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n
from core.utils import get_xml
from plex.live_tv import tune_dvr
from plex.live_tv import tune_plex
from plex.network import Plex

LOG = Logger()

#: What Kodi should be told a stream is, so it does not fetch it once to find
#: out for itself.
MIME_TYPES = {
    '.m3u8': 'application/vnd.apple.mpegurl',
    '.mpd': 'application/dash+xml',
}


def run(context):
    source = context.params.get('live_source', '')

    # a free channel is played straight from the account provider; loading the
    # server list would spend a discovery round trip nothing here uses
    context.plex_network = Plex(context.settings, load=source != 'plex')

    channel = {
        'source': source,
        'key': context.params.get('live_key', ''),
        'dvr': context.params.get('live_dvr', ''),
        'base': context.params.get('live_base', ''),
        'stream': context.params.get('live_stream', ''),
    }

    url = _tune(context, channel)

    if not url:
        xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                      message=i18n('Could not start the channel'),
                                      icon=CONFIG['icon'])
        xbmcplugin.setResolvedUrl(get_handle(), False, xbmcgui.ListItem(offscreen=True))
        return

    LOG.debug('Live TV URL to play: %s' % url)
    xbmcplugin.setResolvedUrl(get_handle(), True, _list_item(url))


def _list_item(url):
    """The stream, described well enough that Kodi can start it right away."""
    list_item = xbmcgui.ListItem(path=url, offscreen=True)

    mime_type = _mime_type(url)
    if not mime_type:
        return list_item

    list_item.setMimeType(mime_type)
    # without a lookup Kodi trusts the type above instead of fetching the
    # stream once only to read its content type
    list_item.setContentLookup(False)

    if xbmc.getCondVisibility('System.HasAddon(inputstream.adaptive)'):
        # the adaptive demuxer joins a live playlist at its edge; the built-in
        # one reads its way there
        list_item.setProperty('inputstream', 'inputstream.adaptive')
        LOG.debug('Playing through inputstream.adaptive as %s' % mime_type)

    return list_item


def _mime_type(url):
    # the path can carry both a query and the header suffix Kodi is handed
    path = url.split('|')[0].split('?')[0].lower()

    for suffix, mime_type in MIME_TYPES.items():
        if path.endswith(suffix):
            return mime_type

    return ''


def _tune(context, channel):
    if channel['source'] == 'plex':
        return tune_plex(context.plex_network, channel)

    if channel['source'] == 'dvr':
        server = context.plex_network.get_server_from_uuid(
            context.params.get('server_uuid'))
        if server is None:
            LOG.error('No server for uuid %s' % context.params.get('server_uuid'))
            return None

        return _shortened(context, server, tune_dvr(context, server, channel))

    LOG.error('Unknown Live TV source: %s' % channel['source'])
    return None


def _shortened(context, server, url):
    """Trade a long transcode URL for the session it hands out.

    Same reason as the channel playback in ``routes/play/video_channel.py``:
    Kodi refuses an HLS request over 1024 bytes, and a tuned transcode carries
    every profile setting in its query.
    """
    if not url or len(url) <= 1000 or '.m3u8' not in url:
        return url

    LOG.debug('Kodi HLS limit detected, will pre-fetch m3u8 playlist')
    playlist = get_xml(context, url)

    if not playlist or '# EXTM3U' not in playlist:
        LOG.debug('Unable to get valid m3u8 playlist from transcoder')
        return url

    session = playlist.split()[-1]
    return server.join_url(server.get_url_location(),
                           'video/:/transcode/segmented/%s?t=1' % session)
