# -*- coding: utf-8 -*-

from urllib.parse import quote_plus

from core.logger import Logger

LOG = Logger()


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


def get_media_data(tag_dict):
    """
        Extra the media info_labels from the XML
        @input: dict of <media /> tag attributes
        @output: dict of required values
    """
    audio_codec_map = {
        'aac': 'AAC',
        'ac3': 'Dolby Digital',
        'dca': 'DTS',
        'dca-ma': 'DTS-HD MA',
        'eac3': 'Dolby Digital+',
        'mp2': 'MP2',
        'mp3': 'MP3',
        'flac': 'FLAC',
        'pcm': 'PCM',
        'truehd': 'Dolby TrueHD'
    }

    video_codec_map = {
        'av1': 'AV1',
        'h264': 'H264',
        'hevc': 'H265',
        'mpeg2video': 'MPEG-2',
        'mpeg4': 'MPEG-4',
        'vc1': 'VC1'
    }

    resolution_map = {
        'sd': 'SD',
        '480': '480p',
        '576': '576p',
        '720': '720p',
        '1080': '1080p',
        '4k': '4K'
    }

    audio_channels_map = {
        '1': '1.0',
        '2': '2.0',
        '3': '2.1',
        '4': '4.0',
        '5': '4.1',
        '6': '5.1',
        '7': '6.1',
        '8': '7.1'
    }

    audio_channels_raw = tag_dict.get('audioChannels', '')
    bitrate_raw = tag_dict.get('bitrate', '')
    try:
        bitrate_mbps = round(int(bitrate_raw) / 1000, 1)
        bitrate = f"{bitrate_mbps} Mbps"
    except (ValueError, TypeError):
        bitrate = ''
    codec_audio = tag_dict.get('audioCodec', '')
    codec_video = tag_dict.get('videoCodec', '')
    resolution_video = tag_dict.get('videoResolution', '')

    default_channels = ('%s.0' % audio_channels_raw
                        if audio_channels_raw.isdigit() else audio_channels_raw)
    audio_channels = audio_channels_map.get(audio_channels_raw, default_channels)
    codec_audio = audio_codec_map.get(codec_audio, codec_audio)
    codec_video = video_codec_map.get(codec_video, codec_video)
    resolution_video = resolution_map.get(resolution_video, resolution_video)

    audio_full = f"{codec_audio} {audio_channels}".strip() if codec_audio or audio_channels else ''

    codec_parts = [part for part in [resolution_video, codec_video, audio_full, bitrate] if part]
    codec = " · ".join(codec_parts)

    stream_info_video = {
        'codec': tag_dict.get('videoCodec', ''),
        'aspect': float(tag_dict.get('aspectRatio', '1.78')),
        'height': int(tag_dict.get('height', 0)),
        'width': int(tag_dict.get('width', 0)),
        'duration': int(tag_dict.get('duration', 0)) / 1000
    }
    stream_info_audio = {
        'codec': codec,
        'channels': 0
    }

    return {
        'VideoResolution': tag_dict.get('videoResolution', ''),
        'VideoCodec': tag_dict.get('videoCodec', ''),
        'AudioCodec': tag_dict.get('audioCodec', ''),
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
        'cast': [],
        'collections': [],
        'director': [],
        'genre': [],
        'writer': [],
    }

    media_tag = data.find('Media')
    if media_tag is not None:
        metadata['attributes'] = dict(media_tag.items())

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
