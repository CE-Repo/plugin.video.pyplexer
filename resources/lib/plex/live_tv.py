# -*- coding: utf-8 -*-

"""Live TV: the tuner behind a server's DVR, and Plex' own free channels.

Neither lineup is a documented API, and Plex has moved both between paths over
the years.  Every lookup here therefore walks a list of candidate paths and
keeps the first answer that holds something channel shaped.  Which candidate
won, and the attributes the first channel carried, are written to the log, so
a layout that none of them matches can be read off a debug log instead of
guessed at a second time.
"""

import xml.etree.ElementTree as ETree
from urllib.parse import urlencode

from core.logger import Logger
from plex.network import PROVIDER_DISCOVER
from plex.network import PROVIDER_EPG

LOG = Logger('livetv')

#: Where a server has kept the channel lineup of its DVR.  ``{dvr}`` and
#: ``{device}`` are filled in from what /livetv/dvrs reports.
DVR_LINEUP_PATHS = (
    '/livetv/dvrs/{dvr}/channels',
    '/livetv/dvrs/{dvr}/lineups/channels',
    '/media/grabbers/devices/{device}/channels',
)

#: ... and where it has accepted a request to tune one of them.
DVR_TUNE_PATHS = (
    '/livetv/dvrs/{dvr}/channels/{channel}/tune',
    '/livetv/dvrs/{dvr}/tune/{channel}',
)

#: The free lineup Plex serves from its own account providers.
PLEX_LINEUP_PATHS = (
    (PROVIDER_EPG, '/lineups/plex/channels'),
    (PROVIDER_EPG, '/channels'),
    (PROVIDER_DISCOVER, '/livetv/lineups/channels'),
)

#: Elements that have carried a channel in any of those answers.
CHANNEL_TAGS = ('ChannelMapping', 'Channel', 'MediaGrabberChannel',
                'LiveTVChannel', 'Directory', 'Video')

#: What a part key looks like when it already is the stream, rather than a
#: path to the metadata that holds one.
_STREAM_MARKERS = ('.m3u8', '.mpd', '/library/parts/')

_TITLE_KEYS = ('title', 'name', 'callSign', 'channelTitle', 'channelCallSign')
_NUMBER_KEYS = ('vcn', 'channelVcn', 'number', 'channelIdentifier')
_LOGO_KEYS = ('thumb', 'channelThumb', 'channelLogo', 'art', 'icon')
_KEY_KEYS = ('channelKey', 'key', 'gridKey', 'channelIdentifier', 'id')
_SUMMARY_KEYS = ('summary', 'description', 'tagline')


def dvr_channels(server):
    """Return the channels of one server's DVR; empty when it has none."""
    channels = []

    for dvr_key, device_key in _dvr_identifiers(server):
        for template in DVR_LINEUP_PATHS:
            if '{device}' in template and not device_key:
                continue

            path = template.format(dvr=dvr_key, device=device_key)
            found = _channels_from_tree(_server_xml(server, path), 'dvr',
                                        dvr_key=dvr_key, server=server)
            if not found:
                continue

            LOG.debug('%s: %s answered with %s channel(s)' %
                      (server.get_name(), path, len(found)))
            channels += found
            break
        else:
            LOG.debug('%s: no lineup path answered for DVR %s' %
                      (server.get_name(), dvr_key))

    return _unique(channels)


def plex_channels(plex_network):
    """Return the free channels of the signed-in account; empty when none."""
    if not plex_network.is_myplex_signedin():
        LOG.debug('Free channels skipped, not signed into myPlex')
        return []

    for base, path in PLEX_LINEUP_PATHS:
        found = _channels_from_tree(plex_network.provider_xml(base, path), 'plex',
                                    base=base)
        if found:
            LOG.debug('%s%s answered with %s channel(s)' % (base, path, len(found)))
            return _unique(found)

    LOG.debug('No provider answered with a free lineup')
    return []


def tune_dvr(context, server, channel):
    """Ask a server to tune one channel and return a URL Kodi can play."""
    stream = channel.get('stream') or ''

    if not stream:
        for template in DVR_TUNE_PATHS:
            path = template.format(dvr=channel.get('dvr', ''),
                                   channel=channel.get('key', ''))
            stream = _stream_from_tree(_server_xml(server, path, method='post'))
            if stream:
                LOG.debug('%s: tuned through %s' % (server.get_name(), path))
                break
        else:
            LOG.error('%s: no tune path answered for channel %s' %
                      (server.get_name(), channel.get('key')))
            return None

    if stream.startswith('http'):
        return stream

    if context.settings.always_transcode():
        url, _session = server.get_universal_transcode(stream)
        return url

    return server.get_kodi_header_formatted_url(stream)


def tune_plex(plex_network, channel):
    """Return a playable URL for one of Plex' own free channels."""
    base = channel.get('base') or PROVIDER_EPG
    stream = channel.get('stream') or ''

    if not stream:
        # the lineup named the channel but kept the stream in its metadata
        stream = _stream_from_tree(
            plex_network.provider_xml(base, '/library/metadata/%s' % channel.get('key', '')))

    if stream and not stream.startswith('http') and not _is_stream(stream):
        # a path to metadata rather than to the stream itself
        stream = _stream_from_tree(plex_network.provider_xml(base, stream)) or ''

    if not stream:
        LOG.error('No stream found for free channel %s' % channel.get('key'))
        return None

    if not stream.startswith('http'):
        # the lineup hands out paths relative to the provider that served it
        stream = '%s%s' % (base, stream if stream.startswith('/') else '/' + stream)

    return _with_account_params(plex_network, stream)


def _dvr_identifiers(server):
    """Return the (DVR, first device) key pairs a server reports."""
    tree = _server_xml(server, '/livetv/dvrs')
    if tree is None:
        return []

    pairs = []
    for dvr in tree.iter('Dvr'):
        dvr_key = _last_segment(dvr.get('key') or dvr.get('uuid') or '')
        if not dvr_key:
            continue

        device = dvr.find('Device')
        device_key = ''
        if device is not None:
            device_key = _last_segment(device.get('key') or device.get('uuid') or '')

        pairs.append((dvr_key, device_key))

    LOG.debug('%s: DVR(s) reported: %s' % (server.get_name(), pairs or 'none'))
    return pairs


def _server_xml(server, path, method='get'):
    """One request to a server that tolerates every way it can go wrong."""
    try:
        if method == 'post':
            tree = ETree.fromstring(server.post(path))
        else:
            tree = server.processed_xml(path)
    except Exception as error:  # pylint: disable=broad-except
        # an absent DVR answers with anything from a 404 to unparsable html
        LOG.debug('%s: %s failed: %s' % (server.get_name(), path, error))
        return None

    if tree is None or tree.tag == 'message':
        LOG.debug('%s: %s did not answer with a container' % (server.get_name(), path))
        return None

    return tree


def _channels_from_tree(tree, source, dvr_key='', server=None, base=''):
    if tree is None:
        return []

    channels = []
    first = None
    for element in tree.iter():
        if element.tag not in CHANNEL_TAGS:
            continue

        channel = _channel_from_element(element, source, dvr_key, server, base)
        if channel:
            channels.append(channel)
            first = first if first is not None else element

    if first is not None:
        # the names Plex used this time, so an unread attribute is one log away
        LOG.debug('First channel was a <%s> carrying %s' %
                  (first.tag, sorted(first.attrib)))

    return channels


def _channel_from_element(element, source, dvr_key, server, base=''):
    if element.get('enabled') == '0':
        return None  # a lineup carries the channels the DVR was told to skip

    title = _attribute(element, _TITLE_KEYS)
    key = _attribute(element, _KEY_KEYS)

    if not title or not key:
        return None

    part = element.find('.//Part')

    return {
        'source': source,
        'title': title,
        'number': _channel_number(_attribute(element, _NUMBER_KEYS)),
        'logo': _attribute(element, _LOGO_KEYS),
        'summary': _attribute(element, _SUMMARY_KEYS),
        'key': key,
        'dvr': dvr_key,
        'base': base,
        'stream': part.get('key', '') if part is not None else '',
        'server_uuid': server.get_uuid() if server is not None else '',
    }


def _is_stream(key):
    return any(marker in key for marker in _STREAM_MARKERS)


def _channel_number(number):
    """Drop the placeholder Plex gives a channel that has no number.

    Only a tuner hands out real numbers; the free lineup fills the field with
    zeroes, which would otherwise sit in front of every single title.
    """
    return number if number.strip('0.') else ''


def _stream_from_tree(tree):
    """Return the first playable part of a tune or metadata answer."""
    if tree is None:
        return ''

    part = tree.find('.//Part')
    if part is not None and part.get('key'):
        return part.get('key')

    for tag in ('MediaSubscription', 'Media', 'Video'):
        element = tree.find('.//%s' % tag)
        if element is not None and element.get('key'):
            return element.get('key')

    return ''


def _with_account_params(plex_network, url):
    params = urlencode(plex_network.plex_identification_header())
    return '%s%s%s' % (url, '&' if '?' in url else '?', params)


def _attribute(element, names):
    for name in names:
        value = element.get(name)
        if value:
            return str(value)
    return ''


def _last_segment(value):
    return str(value).rstrip('/').split('/')[-1]


def _unique(channels):
    """Drop the repeats a lineup and its guide hand out for one channel."""
    seen = set()
    unique = []
    for channel in channels:
        marker = (channel['source'], channel['server_uuid'], channel['key'])
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(channel)
    return unique
