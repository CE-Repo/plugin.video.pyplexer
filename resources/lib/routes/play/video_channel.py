# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.logger import Logger
from core.utils import get_master_server
from core.utils import get_xml
from playback.engine import monitor_channel_transcode_playback
from plex.network import Plex
from storage.data_cache import DATA_CACHE

LOG = Logger()


def run(context, url, prefix=None, indirect=None, transcode=False):
    context.plex_network = Plex(context.settings, load=True)

    server = context.plex_network.get_server_from_url(url)
    if 'node.plexapp.com' in url:
        server = get_master_server(context)

    session = None

    if indirect:
        # Probably should transcode this
        if url.startswith('http'):
            url = '/' + url.split('/', 3)[3]
            transcode = True

        url, session = server.get_universal_transcode(url)

    # if we have a plex URL, then this is a transcoding URL
    if 'plex://' in url:
        LOG.debug('found webkit video, pass to transcoder')
        if not prefix:
            prefix = 'system'
            url, session = server.get_universal_transcode(url)

        # Workaround for Kodi HLS request limit of 1024 byts
        if len(url) > 1000:
            LOG.debug('Kodi HLS limit detected, will pre-fetch m3u8 playlist')

            playlist = get_xml(context, url)

            if not playlist or '# EXTM3U' not in playlist:
                LOG.debug('Unable to get valid m3u8 playlist from transcoder')
                return

            server = context.plex_network.get_server_from_url(url)
            session = playlist.split()[-1]
            url = server.join_url(server.get_url_location(),
                                  'video/:/transcode/segmented/%s?t=1' % session)

    LOG.debug('URL to Play: %s ' % url)
    LOG.debug('Prefix is: %s' % prefix)

    # If this is an Apple movie trailer, add User Agent to allow access
    if 'trailers.apple.com' in url:
        url = url + '|User-Agent=QuickTime/7.6.9 (qtver=7.6.9;os=Windows NT 6.1Service Pack 1)'

    LOG.debug('Final URL is: %s' % url)
    xbmcplugin.setResolvedUrl(get_handle(), True, _list_item(url))

    _monitor_transcode(context, server, session, transcode)
    DATA_CACHE.delete_cache(True)


def _list_item(url):
    return xbmcgui.ListItem(path=url, offscreen=True)


def _monitor_transcode(context, server, session, transcode):
    if session and transcode:
        try:
            monitor_channel_transcode_playback(context, server, session)
        except Exception:  # pylint: disable=broad-except
            LOG.debug('Unable to start transcode monitor')
    else:
        LOG.debug('Not starting monitor')
