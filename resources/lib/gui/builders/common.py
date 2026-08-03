# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ETree
from urllib.parse import quote_plus

from artwork.fanart_tv import CLEARLOGO_ATTRIBUTE
from artwork.fanart_tv import THUMB_ATTRIBUTE
from core.logger import Logger
from playback.quality import describe_short
from playback.quality import kodi_audio_codec
from playback.quality import kodi_hdr_type
from playback.quality import media_details

LOG = Logger()


def is_watchlisted(context, data):
    """Return the actual Plex Watchlist state for a movie or show."""
    if data.get('watchlistedAt') is not None:
        return True
    if not context.plex_network.is_myplex_signedin():
        return False

    guid = data.get('guid') or ''
    rating_key = guid.rsplit('/', 1)[-1] if guid else ''
    return bool(rating_key and
                context.plex_network.is_provider_watchlisted(rating_key))


def get_link_url(server, url, path_data):
    path = path_data.get('key', '')

    LOG.debug('Path is %s' % path)

    if path == '':
        LOG.debug('Empty Path')
        return ''

    # If key starts with http, then return it
    if path.startswith('http'):
        LOG.debug('Detected http(s) link')
        return path

    # If key starts with a / then prefix with server address
    if path.startswith('/'):
        LOG.debug('Detected base path link')
        return server.join_url(server.get_url_location(), path)

    # If key starts with plex:// then it requires transcoding
    if path.startswith('plex:'):
        LOG.debug('Detected plex link')
        components = path.split('&')
        append_component = components.append
        for idx in components:
            if 'prefix=' in idx:
                del components[components.index(idx)]
                break
        if path_data.get('identifier') is not None:
            append_component('identifier=' + path_data['identifier'])

        path = '&'.join(components)
        return 'plex://' + server.get_location() + '/' + '/'.join(path.split('/')[3:])

    if path.startswith('rtmp'):
        LOG.debug('Detected RTMP link')
        return path

    # Any thing else is assumed to be a relative path and is built on existing url
    LOG.debug('Detected relative link')
    return server.join_url(url, path)


def get_thumb_image(context, server, data, width=720, height=720):
    """
        Simply take a URL or path and determine how to format for images
        @ input: elementTree element, server name
        @ return formatted URL
    """
    if context.settings.skip_images():
        return ''

    thumbnail = data.get('thumb', '').split('?t')[0]

    if thumbnail.startswith('http'):
        return thumbnail

    if thumbnail.startswith('/'):
        if context.settings.full_resolution_thumbnails():
            return server.get_kodi_header_formatted_url(thumbnail)

        thumbnail = quote_plus('http://localhost:32400' + thumbnail)
        return server.get_kodi_header_formatted_url('/photo/:/transcode?url=%s&width=%s&height=%s' %
                                                    (thumbnail, width, height))

    # No Plex thumbnail: return empty so Kodi/the skin uses its native default art
    return ''


def get_landscape_image(context, data):
    """Return the external landscape thumb pre-resolved for a video item."""
    if context.settings.skip_images():
        return ''
    return data.get(THUMB_ATTRIBUTE, '')


def get_banner_image(context, server, data, width=720, height=720):
    """
        Simply take a URL or path and determine how to format for images
        @ input: elementTree element, server name
        @ return formatted URL
    """
    if context.settings.skip_images():
        return ''

    banner = data.get('banner', '').split('?t')[0]

    if banner.startswith('http'):
        return banner

    if banner.startswith('/'):
        if context.settings.full_resolution_thumbnails():
            return server.get_kodi_header_formatted_url(banner)

        banner = quote_plus('http://localhost:32400' + banner)
        return server.get_kodi_header_formatted_url('/photo/:/transcode?url=%s&width=%s&height=%s' %
                                                    (banner, width, height))

    return ''


def get_clearlogo_image(context, server, data):
    """Return the resolved external logo, then Plex's clearLogo fallback.

    An episode carries the logo of its show, which is what a skin wants to put
    on screen.  The image is handed over as it is: it is a PNG that lives from
    its transparency, and the photo transcoder would flatten it onto a
    background.
    """
    if context.settings.skip_images() or data is None:
        return ''

    logo = data.get(CLEARLOGO_ATTRIBUTE) or ''
    if not logo:
        for image in data.findall('Image'):
            if (image.get('type') or '').lower() == 'clearlogo':
                logo = image.get('url') or ''
                break

    if not logo:
        logo = data.get('clearLogo') or ''

    if logo.startswith('http'):
        return logo

    if logo.startswith('/'):
        return server.get_kodi_header_formatted_url(logo)

    return ''


def get_fanart_image(context, server, data, width=1280, height=720):
    """
        Simply take a URL or path and determine how to format for fanart
        @ input: elementTree element, server name
        @ return formatted URL for photo resizing
    """
    if context.settings.skip_images():
        return ''

    fanart = data.get('art', '')

    if fanart.startswith('http'):
        return fanart

    if fanart.startswith('/'):
        if context.settings.full_resolution_fanart():
            return server.get_kodi_header_formatted_url(fanart)

        return server.get_kodi_header_formatted_url('/photo/:/transcode?url=%s&width=%s&height=%s' %
                                                    (quote_plus('http://localhost:32400' + fanart),
                                                     width, height))

    return ''


def _as_int(value, fallback=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _as_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def get_media_data(tag_dict, media=None, item=None, for_player=False):
    """
        Extra the media info_labels from the XML
        @input: dict of <media /> tag attributes, optionally the element itself
                so the streams and parts below it can be read as well, the item
                it belongs to for the edition, and whether the listing is being
                built for a player rather than for Kodi
        @output: dict of required values
    """
    if media is None:
        media = ETree.Element('Media', {key: str(value)
                                        for key, value in tag_dict.items()})

    details = media_details(media, item)
    audio_codec = kodi_audio_codec(details)
    channels = _as_int(tag_dict.get('audioChannels'))

    # Kodi types these strictly: a float where an int belongs makes the whole
    # video stream be dropped, and with it the resolution and HDR flags
    stream_info_video = {
        'codec': tag_dict.get('videoCodec', ''),
        'aspect': _as_float(tag_dict.get('aspectRatio'), 1.78),
        'height': _as_int(tag_dict.get('height')),
        'width': _as_int(tag_dict.get('width')),
        'duration': _as_int(tag_dict.get('duration')) // 1000,
        # what a skin compares against for its HDR flag
        'hdrtype': kodi_hdr_type(details),
    }

    stream_info_audio = {
        'codec': audio_codec,
        'channels': channels,
    }

    languages = details.get('languages') or []
    if languages:
        stream_info_audio['language'] = languages[0].lower()

    if for_player:
        # a player has no flags to show, it writes the stream details into its
        # label instead - so it gets the description and nothing else, or it
        # prints the resolution, the codec and the running time around it
        # the channel count has to be said out loud as zero: left out, Kodi
        # stores its own -1 and the player prints that as '-1 CH'
        stream_info_audio = {'codec': describe_short(details), 'channels': 0}
        stream_info_video = {}

    return {
        'VideoResolution': tag_dict.get('videoResolution', ''),
        'VideoCodec': tag_dict.get('videoCodec', ''),
        'AudioCodec': audio_codec,
        'AudioChannels': tag_dict.get('audioChannels', ''),
        'VideoAspect': tag_dict.get('aspectRatio', ''),
        'stream_info': {
            'video': stream_info_video,
            'audio': stream_info_audio,
        },
    }


def get_metadata(context, data):
    metadata = {
        'attributes': {},
        'media': None,  # the element itself, for the streams below it
        'cast': [],
        'collections': [],
        'director': [],
        'genre': [],
        'writer': [],
    }

    media_tag = data.find('Media')
    if media_tag is not None:
        metadata['attributes'] = dict(media_tag.items())
        metadata['media'] = media_tag

    if not context.settings.skip_metadata():
        append_genre = metadata['genre'].append
        append_writer = metadata['writer'].append
        append_director = metadata['director'].append
        append_cast = metadata['cast'].append
        append_collections = metadata['collections'].append

        for child in data:
            if child.tag == 'Genre':
                append_genre(child.get('tag'))
            elif child.tag == 'Writer':
                append_writer(child.get('tag'))
            elif child.tag == 'Director':
                append_director(child.get('tag'))
            elif child.tag == 'Role':
                append_cast(child.get('tag'))
            elif child.tag == 'Collection':
                append_collections(child.get('tag'))

    return metadata
