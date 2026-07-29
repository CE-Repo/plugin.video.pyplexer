# -*- coding: utf-8 -*-

"""Looks for a better version of the item that is about to be played.

Plex can hold several versions of the same title: as multiple Media elements on
one item, as its own item in another library on the same server (a 4K library
next to a Full HD one), or as a copy on another server of the account.  Before
playback starts the servers are asked - in parallel and with a hard time limit -
whether they hold the same title, and anything that beats the version Kodi would
have played is offered in a selection dialog.

Movies are matched by their Plex guid, falling back to title and year because
libraries scanned with different agents do not share a guid.  Episodes are
matched by guid as well, falling back to their show, season and episode number.
"""

import re
import threading
import time
from urllib.parse import quote
from urllib.parse import urlencode

import xbmcgui  # pylint: disable=import-error

from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n_or
from core.utils import attach_media_streams

LOG = Logger('quality')

#: Returned by QualitySearch.run() when the dialog was dismissed - the viewer
#: asked for a choice and took none, so nothing is played.
CANCELLED = object()

MAX_SERVERS = 8  # servers queried in parallel
MAX_VERSIONS = 12  # versions collected per server
MAX_SHOWS = 4  # libraries opened per server when matching an episode by title
MIN_BITRATE_GAIN = 1.15  # 15% more bitrate before a version counts as better
MIN_BITRATE_DELTA = 1.0  # ... and at least 1 Mbps more

HDR_MARKERS = ('hdr', 'pq', 'hlg', 'smpte2084', 'bt2020')

#: Marketing names for the video codecs Plex reports on a Media element.
VIDEO_NAMES = {
    'av1': 'AV1',
    'h264': 'H264',
    'hevc': 'H265',
    'mpeg1video': 'MPEG-1',
    'mpeg2video': 'MPEG-2',
    'mpeg4': 'MPEG-4',
    'vc1': 'VC1',
    'vp8': 'VP8',
    'vp9': 'VP9',
}

#: Where a release comes from, read off the file name - the difference between
#: a 74 Mb/s remux and a 20 Mb/s web release is worth naming.
SOURCE_MARKERS = (
    ('remux', 'Remux'),
    ('bluray', 'BluRay'),
    ('blu-ray', 'BluRay'),
    ('bdrip', 'BDRip'),
    ('webdl', 'WEB-DL'),
    ('web-dl', 'WEB-DL'),
    ('webrip', 'WEBRip'),
    ('hdtv', 'HDTV'),
    ('dvdrip', 'DVD'),
)

#: Languages are shown as the short tag Plex hands out, upper cased.
MAX_LANGUAGES = 3

#: Marketing names for the audio codecs Plex reports on a Media element.
AUDIO_NAMES = {
    'aac': 'AAC',
    'aac_latm': 'AAC',
    'ac3': 'Dolby Digital',
    'ac4': 'Dolby AC-4',
    'alac': 'ALAC',
    'dca': 'DTS',
    'dts': 'DTS',
    'eac3': 'Dolby Digital Plus',
    'flac': 'FLAC',
    'lpcm': 'PCM',
    'mp2': 'MP2',
    'mp3': 'MP3',
    'opus': 'Opus',
    'pcm': 'PCM',
    'truehd': 'Dolby TrueHD',
    'vorbis': 'Vorbis',
    'wmapro': 'WMA Pro',
    'wmav2': 'WMA',
}

#: The DTS family is told apart by the profile of its audio stream.
DTS_PROFILES = {
    '96/24': 'DTS 96/24',
    'dts_express': 'DTS Express',
    'dts_x': 'DTS:X',
    'dtsx': 'DTS:X',
    'es': 'DTS-ES',
    'es discrete': 'DTS-ES',
    'es matrix': 'DTS-ES',
    'express': 'DTS Express',
    'hra': 'DTS-HD HRA',
    'lbr': 'DTS Express',
    'ma': 'DTS-HD MA',
    'x': 'DTS:X',
}

DTS_CODECS = ('dca', 'dts', 'dca-ma', 'dts-hd', 'dtshd')

CHANNEL_LAYOUTS = {
    1: '1.0',
    2: '2.0',
    3: '2.1',
    4: '4.0',
    5: '4.1',
    6: '5.1',
    7: '6.1',
    8: '7.1',
    9: '8.1',
    10: '9.1',
    12: '11.1',
}


def resolution_height(value):
    """Plex mixes 'sd', '4k' and plain heights in videoResolution."""
    text = str(value or '').lower()
    if text == 'sd':
        return 480
    if text == '4k':
        return 2160

    try:
        return int(text)
    except (TypeError, ValueError):
        return 0


def resolution_label(value):
    """Label as viewers know it: 4K, 1080p, 720p, ..."""
    text = str(value or '').lower()
    if text == 'sd':
        return 'SD'

    height = resolution_height(value)
    if not height:
        return ''

    if height > 2400:
        return '8K'
    if height > 1088:
        return '4K'

    return '%dp' % height


def resolution_rank(height):
    """Bucket used for comparing, so 1082 does not beat 1080."""
    if height > 1088:
        return 4
    if height >= 1080:
        return 3
    if height >= 720:
        return 2
    if height > 0:
        return 1
    return 0


def audio_stream(media):
    """The audio stream that will be played, when the response carries one -
    /library/all and allLeaves only return the Media attributes."""
    fallback = None

    for stream in media.iter('Stream'):
        if stream.get('streamType') != '2':
            continue
        if stream.get('selected') == '1':
            return stream
        if fallback is None:
            fallback = stream

    return fallback


def audio_label(media):
    """'Dolby Digital Plus 7.1', 'DTS-HD MA 7.1', 'Dolby TrueHD 7.1 (Atmos)'."""
    codec = (media.get('audioCodec') or '').lower()
    channels = media.get('audioChannels')
    # a listing without streams still names the profile on the Media element,
    # which is what tells DTS:X from plain DTS
    profile = (media.get('audioProfile') or '').lower()
    layout = ''
    described = ''

    stream = audio_stream(media)
    if stream is not None:
        codec = (stream.get('codec') or codec).lower()
        channels = stream.get('channels') or channels
        profile = (stream.get('profile') or profile).lower()
        layout = stream.get('audioChannelLayout') or ''
        described = ' '.join(filter(None, [stream.get('displayTitle'),
                                           stream.get('extendedDisplayTitle'),
                                           stream.get('title')])).lower()

    name = _audio_name(codec, profile, described)
    if not name:
        return ''

    parts = [name, _channel_layout(channels, layout)]
    if _is_atmos(profile, described):
        parts.append('(Atmos)')

    return ' '.join([part for part in parts if part])


def _audio_name(codec, profile, described):
    if not codec:
        return ''

    if codec in DTS_CODECS:
        haystack = '%s %s' % (profile, described)
        if any(marker in haystack for marker in ('dts:x', 'dts-x', 'dtsx')):
            return 'DTS:X'
        if profile in DTS_PROFILES:
            return DTS_PROFILES[profile]
        # Plex writes compound profiles such as 'ma + dts:x'
        for key, name in DTS_PROFILES.items():
            if key in [part.strip() for part in profile.replace('+', ' ').split()]:
                return name
        if codec in ('dca-ma', 'dts-hd', 'dtshd'):
            return 'DTS-HD MA'
        return 'DTS'

    return AUDIO_NAMES.get(codec, codec.upper())


def _is_atmos(profile, described):
    haystack = '%s %s' % (profile, described)
    return 'atmos' in haystack or 'joc' in haystack


def _channel_layout(channels, layout):
    # '7.1(side)' -> '7.1', but 'stereo' and 'mono' fall through to the count
    layout = (layout or '').split('(')[0].strip()
    if re.match(r'^\d+\.\d+$', layout):
        return layout

    try:
        count = int(channels)
    except (TypeError, ValueError):
        return ''

    return CHANNEL_LAYOUTS.get(count, '%d.0' % count if count else '')


def video_stream(media):
    """The video stream, when the response carries one."""
    for stream in media.iter('Stream'):
        if stream.get('streamType') == '1':
            return stream

    return None


def dolby_vision_profile(source):
    """The DOVIProfile, which decides whether a player can show the file."""
    return str(source.get('DOVIProfile') or '').strip()


def hdr_label(media):
    """'DV Profile 7', 'Dolby Vision', 'HDR10+', 'HDR10' or 'HLG'.

    Plex names Dolby Vision through the DOVI attributes of the video stream and
    the transfer curve through colorTrc; a listing that carries neither is left
    with the profile on the Media element, which only ever says 'HDR' at best.
    """
    dolby_vision = False
    profile = ''
    hdr = ''

    stream = video_stream(media)
    sources = [media] if stream is None else [stream, media]

    for source in sources:
        if source.get('DOVIPresent') == '1' or source.get('DOVIProfile'):
            dolby_vision = True
            profile = profile or dolby_vision_profile(source)

        described = ' '.join([str(source.get(key) or '') for key in
                              ('colorTrc', 'videoProfile', 'displayTitle',
                               'extendedDisplayTitle')]).lower()

        if not hdr:
            if 'hdr10+' in described or 'hdr10plus' in described:
                hdr = 'HDR10+'
            elif 'smpte2084' in described or 'hdr10' in described:
                hdr = 'HDR10'
            elif 'arib-std-b67' in described or 'hlg' in described:
                hdr = 'HLG'
            elif 'dovi' in described or 'dolby vision' in described:
                dolby_vision = True
            elif 'hdr' in described:
                hdr = 'HDR'

    named_hdr, named_dv = _hdr_from_file_name(media)

    # Plex reports HDR10+ as plain HDR10, and a listing carries no streams at
    # all - in both cases the file name is the only thing left to go by
    if named_hdr == 'HDR10+' and hdr == 'HDR10':
        hdr = 'HDR10+'
    elif not hdr:
        hdr = named_hdr
    if named_dv:
        dolby_vision = True

    # Dolby Vision carries an HDR10 base layer anyway, so naming both only
    # makes the line longer
    if dolby_vision:
        return 'DV Profile %s' % profile if profile else 'Dolby Vision'

    return hdr


def _file_names(media):
    return ' '.join([str(part.get('file') or '')
                     for part in media.iter('Part')]).lower()


def _hdr_from_file_name(media):
    """Releases are named '[DV HDR10Plus]', '[HDR10]', '[HLG]'.  Only whole
    words count, so 'DVDRip' is not read as Dolby Vision."""
    names = _file_names(media)

    def _word(marker):
        return re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % marker, names) is not None

    hdr = ''
    if 'hdr10plus' in names or 'hdr10+' in names:
        hdr = 'HDR10+'
    elif 'hdr10' in names:
        hdr = 'HDR10'
    elif _word('hlg'):
        hdr = 'HLG'
    elif _word('hdr'):
        hdr = 'HDR'

    return hdr, _word('dv') or 'dolbyvision' in names or 'dolby vision' in names


def source_label(media):
    """'Remux', 'BluRay', 'WEB-DL', ... read off the file name."""
    names = _file_names(media)

    for marker, name in SOURCE_MARKERS:
        if marker in names:
            return name

    return ''


def language_labels(media, stream_type='2'):
    """The languages of the audio (or subtitle) streams, the selected one
    first, as the short tags viewers recognise: ['DE', 'EN']."""
    labels = []

    for stream in sorted(media.iter('Stream'),
                         key=lambda item: 0 if item.get('selected') == '1' else 1):
        if stream.get('streamType') != stream_type:
            continue

        tag = (stream.get('languageTag') or stream.get('languageCode') or '')[:2].upper()
        if tag and tag not in labels:
            labels.append(tag)

    return labels[:MAX_LANGUAGES]


def media_size(media):
    """Size of the version in bytes, the parts of a split file added up."""
    total = 0

    for part in media.iter('Part'):
        try:
            total += int(part.get('size') or 0)
        except (TypeError, ValueError):
            continue

    return total


def size_label(size):
    if size >= 1024 ** 3:
        return '%.1f GB' % (size / 1024 ** 3)
    if size >= 1024 ** 2:
        return '%.0f MB' % (size / 1024 ** 2)

    return ''


def media_details(media, item=None):
    """Normalised description of a single <Media> element.  The item it belongs
    to is only read for the edition, which Plex keeps on the item."""
    try:
        bitrate = round(float(media.get('bitrate', 0)) / 1000, 1)
    except (TypeError, ValueError):
        bitrate = 0.0

    stream = video_stream(media)
    bit_depth = 8
    for source in [media] if stream is None else [stream, media]:
        try:
            found = int(source.get('bitDepth') or 0)
        except (TypeError, ValueError):
            found = 0
        if found:
            bit_depth = found
            break
    else:
        if '10' in str(media.get('videoProfile') or '').split():
            bit_depth = 10  # old servers only report 'main 10'

    codec = media.get('videoCodec')

    return {
        'bitrate': bitrate,
        'bitDepth': bit_depth,
        'height': resolution_height(media.get('videoResolution')),
        'videoResolution': resolution_label(media.get('videoResolution')),
        'container': media.get('container', 'unknown'),
        'codec': codec,
        'codecLabel': VIDEO_NAMES.get((codec or '').lower(), (codec or '').upper()),
        'audio': audio_label(media),
        'audioCodec': media.get('audioCodec'),
        'audioChannels': media.get('audioChannels'),
        'languages': language_labels(media),
        'subtitles': language_labels(media, stream_type='3'),
        'source': source_label(media),
        'size': media_size(media),
        'hdr': hdr_label(media),
        'edition': (item.get('editionTitle') or '') if item is not None else '',
    }


def quality_score(details):
    """Sort key, ordered by the things a viewer notices first."""
    try:
        bitrate = float(details.get('bitrate') or 0)
    except (TypeError, ValueError):
        bitrate = 0.0

    try:
        bit_depth = int(details.get('bitDepth') or 8)
    except (TypeError, ValueError):
        bit_depth = 8

    try:
        height = int(details.get('height') or 0)
    except (TypeError, ValueError):
        height = 0

    return (
        resolution_rank(height),
        1 if details.get('hdr') else 0,
        bit_depth,
        bitrate,
    )


def is_better(candidate, current):
    """A version only counts as better when the gain is actually visible, so a
    handful of kilobits never triggers the dialog."""
    candidate_score = quality_score(candidate)
    current_score = quality_score(current)

    if candidate_score[:3] > current_score[:3]:
        return True
    if candidate_score[:3] < current_score[:3]:
        return False

    return (candidate_score[3] >= current_score[3] * MIN_BITRATE_GAIN and
            candidate_score[3] - current_score[3] >= MIN_BITRATE_DELTA)


def normalise_title(value):
    """Strip everything that differs between two spellings of one title."""
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def part_index_for_media(details, media_index):
    """StreamData holds one details entry per part, sharing the dict of their
    Media; translate a Media position back into the first part that belongs to
    it, which is what MediaSelect works with."""
    if media_index is None:
        return None

    seen = []
    for index, entry in enumerate(details or []):
        if any(entry is known for known in seen):
            continue
        seen.append(entry)
        if len(seen) - 1 == media_index:
            return index

    return None


def kodi_hdr_type(details):
    """The value Kodi keeps in ListItem.HdrType, which is what a skin compares
    against to show its Dolby Vision or HDR flag."""
    hdr = (details.get('hdr') or '').lower()

    if not hdr:
        return ''
    if 'dv' in hdr.split() or 'dolby vision' in hdr:
        return 'dolbyvision'
    if 'hlg' in hdr:
        return 'hlg'

    return 'hdr10'


def kodi_audio_codec(details):
    """The codec name Kodi and the skins know, worked out from the audio that
    was found: 'dtshd_ma_x' for DTS:X, 'truehd_atmos' for Atmos, and so on.

    A skin picks its flag by comparing this name, so 'dca' with a DTS:X profile
    has to arrive as the name that stands for DTS:X.
    """
    audio = (details.get('audio') or '').lower()
    atmos = 'atmos' in audio

    if 'truehd' in audio:
        return 'truehd_atmos' if atmos else 'truehd'
    if 'dolby digital plus' in audio or 'dolby digital+' in audio:
        return 'eac3_ddp_atmos' if atmos else 'eac3'
    if 'dolby digital' in audio:
        return 'ac3'
    if 'dts:x' in audio:
        return 'dtshd_ma_x'
    if 'dts-hd ma' in audio:
        return 'dtshd_ma'
    if 'dts-hd hra' in audio:
        return 'dtshd_hra'
    if 'dts express' in audio:
        return 'dtshd'
    if 'dts' in audio:
        return 'dts'

    return (details.get('audioCodec') or '').lower()


def dynamic_range(details):
    """The HDR format, or 'SDR' for a video that carries none - a viewer should
    not have to read the missing word."""
    if not details.get('videoResolution') and not details.get('height'):
        return ''  # nothing that has a picture

    return details.get('hdr') or 'SDR'


def describe_short(details):
    """What a listing says about an item: the picture and the sound, e.g.
    '4K · DV Profile 7 · Dolby TrueHD 7.1 (Atmos)'.  Where the file comes from
    and how big it is belongs in the version dialog, not under every title."""
    parts = [
        details.get('videoResolution'),
        dynamic_range(details),
        details.get('audio'),
        details.get('edition'),
    ]

    return ' · '.join([part for part in parts if part]) or i18n_or('Unknown', 'Unbekannt')


def describe_file(details):
    """What is left once the picture and the sound have been named: where the
    file comes from, how it is encoded and how big it is - the things that tell
    two copies of one title apart, e.g.
    'Remux · H265 10 Bit · DE/EN · 74.5 Mb/s · 70.5 GB'."""
    depth = details.get('bitDepth') or 8
    video = ' '.join([part for part in [details.get('codecLabel'),
                                        '%d Bit' % depth if depth > 8 else ''] if part])

    bitrate = details.get('bitrate')
    parts = [
        details.get('source'),
        video,
        '/'.join(details.get('languages') or []),
        '%s %s' % (bitrate, i18n_or('Mb/s', 'Mb/s')) if bitrate else '',
        size_label(details.get('size') or 0),
    ]

    return ' · '.join([part for part in parts if part])


def describe(details):
    """Everything in one line, e.g. '4K · DV Profile 7 · Dolby TrueHD 7.1
    (Atmos) · Remux · H265 10 Bit · DE/EN · 74.5 Mb/s · 70.5 GB'.  Everything
    the response did not carry is left out rather than guessed at."""
    parts = [describe_short(details), describe_file(details)]

    return ' · '.join([part for part in parts if part]) or i18n_or('Unknown', 'Unbekannt')


class QualitySearch:
    """Collects the playable versions of an item and, when a better one exists,
    lets the user pick which one to play."""

    def __init__(self, context, server, stream, media_id=None):  # pylint: disable=too-many-positional-arguments
        self.context = context
        self.server = server
        self.stream = stream
        self.media_id = media_id

    def run(self):
        """Returns the selected version, None to play the default one, or
        CANCELLED when the dialog was dismissed and nothing should play."""
        versions = self._local_versions()
        if not versions:
            return None

        current = versions[0]
        candidates = versions + self._other_copies()
        candidates.sort(key=lambda version: quality_score(version['details']), reverse=True)

        for version in candidates:
            LOG.debug('Version on %s: %s%s' % (version['server_name'],
                                               describe(version['details']),
                                               ' (current)' if version is current else ''))

        if self.context.settings.quality_search_always_ask():
            if len(candidates) < 2:
                LOG.debug('Only one version exists, nothing to choose from')
                return None
            return self._ask(candidates, current)

        best = candidates[0]
        if best is current or not is_better(best['details'], current['details']):
            LOG.debug('No better version found, playing the default one')
            return None

        return self._ask(candidates, current)

    def _servers_to_search(self):
        """The current server is always asked for further copies of the title -
        a 4K library sitting next to a Full HD one is the common case - the
        other servers of the account only when the setting allows it."""
        if not (self._guid() or self._title() or self._show()):
            return []

        servers = [self.server]

        if self.context.settings.quality_search_servers():
            servers += [server for server in self.context.plex_network.get_server_list()
                        if not server.is_offline() and not server.is_secondary()
                        and server.get_uuid() != self.server.get_uuid()]

        return servers[:MAX_SERVERS]

    def _guid(self):
        return self.stream.get('extra', {}).get('guid')

    def _show_guid(self):
        return self.stream.get('extra', {}).get('show_guid')

    def _title(self):
        """Movie title; episodes are matched through their show instead."""
        full_data = self.stream.get('full_data', {})
        if full_data.get('mediatype') != 'movie':
            return None
        return full_data.get('title')

    def _year(self):
        try:
            return int(self.stream.get('full_data', {}).get('year') or 0)
        except (TypeError, ValueError):
            return 0

    def _show(self):
        """Show title, season and episode number of the playing episode."""
        full_data = self.stream.get('full_data', {})
        if full_data.get('mediatype') != 'episode':
            return None

        title = full_data.get('tvshowtitle')
        if not title:
            return None

        try:
            season = int(full_data.get('season'))
            episode = int(full_data.get('episode'))
        except (TypeError, ValueError):
            return None

        return title, season, episode

    def _local_versions(self):
        """One entry per <Media> of the item; a Media split over several parts
        (CD1/CD2) is offered once and played from its first part."""
        versions = []
        seen = []

        for index, details in enumerate(self.stream.get('details', [])):
            if any(details is known for known in seen):
                continue
            seen.append(details)
            versions.append({
                'part_index': index,
                'media_index': len(seen) - 1,
                'details': details,
                'server_uuid': self.server.get_uuid(),
                'server_name': self.server.get_name(),
                'library': self.stream.get('extra', {}).get('library') or '',
                'media_id': self.media_id,
                'local': True,
            })

        return versions

    def _other_copies(self):
        """Copies of the title held as their own item, whether in another
        library on this server or on another server of the account."""
        servers = self._servers_to_search()
        if not servers:
            return []

        LOG.debug('Searching %s server(s) for other copies of %s / %s' %
                  (len(servers), self._guid(), self._title() or self._show()))

        results = []
        lock = threading.Lock()
        threads = []

        for server in servers:
            thread = threading.Thread(target=self._lookup, args=(server, results, lock))
            thread.daemon = True
            thread.start()
            threads.append(thread)

        progress = xbmcgui.DialogProgressBG()
        try:
            progress.create(CONFIG['name'],
                            i18n_or('Searching for a better quality...',
                                    'Suche nach besserer Qualität ...'))
        except Exception:  # pylint: disable=broad-except
            progress = None

        deadline = time.time() + self.context.settings.quality_search_timeout()
        try:
            for thread in threads:
                thread.join(max(0.1, deadline - time.time()))
        finally:
            if progress is not None:
                try:
                    progress.close()
                except Exception:  # pylint: disable=broad-except
                    pass

        with lock:
            return list(results)

    def _lookup(self, server, results, lock):
        found = self._by_guid(server)
        way = 'guid'

        if not found:
            # an episode is held as its own item per library, so the copy is
            # reached through the show rather than through the episode guid
            found = self._by_show_guid(server)
            way = 'show guid'

        if not found:
            # libraries scanned with different agents do not share a guid, so
            # fall back to the title before giving up on this server
            found = self._by_title(server)
            way = 'title'

        LOG.debug('%s: %s version(s) found by %s' % (server.get_name(), len(found), way))

        if found:
            with lock:
                results.extend(found)

    def _talk(self, server, url):
        try:
            return server.processed_xml(url)
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('Version lookup failed on %s: %s' % (server.get_name(), error))
            return None

    def _by_guid(self, server):
        guid = self._guid()
        if not guid:
            return []

        # /library/all searches what a library shows on its first page, so an
        # episode has to be asked for as such or it is not found at all
        wanted_type = '&type=4' if self._show() else ''

        tree = self._talk(server, '/library/all?guid=%s%s' %
                          (quote(guid, safe=''), wanted_type))
        if tree is None:
            return []

        return self._versions_from(server, tree.iter('Video'))

    def _by_show_guid(self, server):
        """Find the show by its guid, then the episode by its numbers.

        Every library holds its own copy of a show, so the episode guid only
        ever finds the item that is playing.  The guid of the show is the same
        in every library that scanned it with the Plex agent, whatever title it
        ended up with.
        """
        guid = self._show_guid()
        wanted = self._show()
        if not guid or not wanted:
            return []

        _, season, episode = wanted

        tree = self._talk(server, '/library/all?type=2&guid=%s' % quote(guid, safe=''))
        if tree is None:
            return []

        keys = []
        for element in tree.iter():
            if element.get('type') != 'show':
                continue
            rating_key = element.get('ratingKey')
            if rating_key and rating_key not in keys:
                keys.append(rating_key)

        found = []
        for rating_key in keys[:MAX_SHOWS]:
            leaves = self._talk(server, '/library/metadata/%s/allLeaves' % rating_key)
            if leaves is None:
                continue

            found += self._versions_from(server, self._episode_matches(leaves, season, episode))

        return found

    def _by_title(self, server):
        title = self._title()
        if title:
            tree = self._search(server, title)
            if tree is None:
                return []
            return self._versions_from(server, self._title_matches(tree))

        if self._show():
            return self._by_episode(server)

        return []

    def _search(self, server, query):
        return self._talk(server, '/search?%s' % urlencode({'query': query, 'limit': 30}))

    def _by_episode(self, server):
        """Episodes are looked up through their show: find the show by title,
        then the episode by its season and episode number."""
        title, season, episode = self._show()

        found = []

        for rating_key in self._find_shows(server, title)[:MAX_SHOWS]:
            leaves = self._talk(server, '/library/metadata/%s/allLeaves' % rating_key)
            if leaves is None:
                continue

            found += self._versions_from(server, self._episode_matches(leaves, season, episode))

        if not found:
            LOG.debug('No other copy of %s S%sE%s on %s' %
                      (title, season, episode, server.get_name()))

        return found

    def _find_shows(self, server, title):
        """Rating keys of the show, one per library that holds it.  The global
        search answers first; a library that does not show up there is asked
        through its own section before the server is given up on."""
        wanted = normalise_title(title)

        found = self._shows_from(self._search(server, title), wanted)
        if found:
            return found

        for section in self._show_sections(server):
            tree = self._talk(server, '%s/search?type=2&query=%s' %
                              (section.get_path(), quote(title, safe='')))
            for rating_key in self._shows_from(tree, wanted):
                if rating_key not in found:
                    found.append(rating_key)

        return found

    @staticmethod
    def _show_sections(server):
        try:
            return [section for section in server.get_sections()
                    if section.get_type() == 'show']
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('Sections unavailable on %s: %s' % (server.get_name(), error))
            return []

    @staticmethod
    def _shows_from(tree, wanted):
        """Shows of that name, whatever spelling the library keeps them under -
        one library holds the localised title, the next the original one."""
        if tree is None:
            return []

        found = []

        for directory in tree.iter('Directory'):
            if directory.get('type') != 'show':
                continue

            candidates = (directory.get('title'), directory.get('originalTitle'),
                          directory.get('titleSort'))
            if not any(normalise_title(candidate) == wanted
                       for candidate in candidates if candidate):
                continue

            rating_key = directory.get('ratingKey')
            if rating_key and rating_key not in found:
                found.append(rating_key)

        return found

    @staticmethod
    def _episode_matches(tree, season, episode):
        for video in tree.iter('Video'):
            try:
                if (int(video.get('parentIndex')) == season and
                        int(video.get('index')) == episode):
                    yield video
            except (TypeError, ValueError):
                continue

    def _title_matches(self, tree):
        """Same title, same year, same type - anything looser starts offering
        remakes and making-of features as 'better versions'."""
        wanted = normalise_title(self._title())
        year = self._year()

        for video in tree.iter('Video'):
            if video.get('type') != 'movie':
                continue
            if normalise_title(video.get('title')) != wanted:
                continue

            try:
                found_year = int(video.get('year') or 0)
            except (TypeError, ValueError):
                found_year = 0

            if year and found_year and year != found_year:
                continue

            yield video

    def _versions_from(self, server, videos):
        found = []

        # a search answers without the streams below a Media, so the Dolby
        # Vision profile would be missing on everything but the playing item
        videos = list(videos)
        attach_media_streams(server, videos)

        for video in videos:
            rating_key = video.get('ratingKey')
            if not rating_key or self._is_current_item(server, rating_key):
                continue

            library = self._library_of(server, video)

            for index, media in enumerate(video.iter('Media')):
                found.append({
                    'part_index': None,  # resolved once the item is loaded
                    'media_index': index,
                    'details': media_details(media, video),
                    'server_uuid': server.get_uuid(),
                    'server_name': server.get_name(),
                    'library': library,
                    'media_id': rating_key,
                    'local': False,
                })

            if len(found) >= MAX_VERSIONS:
                break

        return found

    @staticmethod
    def _library_of(server, video):
        """The library an item sits in.  Most responses name it on the item,
        the rest at least carry its id."""
        title = video.get('librarySectionTitle')
        if title:
            return title

        section_id = video.get('librarySectionID')
        if section_id:
            try:
                for section in server.get_sections():
                    if str(section.get_key()) == str(section_id):
                        return section.get_title()
            except Exception as error:  # pylint: disable=broad-except
                LOG.debug('Section lookup failed on %s: %s' % (server.get_name(), error))

        return ''

    def _is_current_item(self, server, rating_key):
        return (server.get_uuid() == self.server.get_uuid() and
                str(rating_key) == str(self.media_id))

    def _ask(self, candidates, current):
        heading = i18n_or('Better quality available', 'Bessere Qualität verfügbar')
        multiple_servers = len({version['server_uuid'] for version in candidates}) > 1

        items = []
        for version in candidates:
            # where the version sits and what it costs on top, with the same
            # words the listings use below it
            item = xbmcgui.ListItem(label=self._version_label(version, current,
                                                              multiple_servers))
            item.setLabel2(describe_short(version['details']))
            item.setArt({'icon': CONFIG['icon']})
            items.append(item)

        selected = xbmcgui.Dialog().select(heading, items, useDetails=True, preselect=0)

        if selected < 0:
            LOG.debug('Version selection cancelled, nothing will be played')
            return CANCELLED

        chosen = candidates[selected]
        LOG.debug('Selected version: %s on %s' %
                  (describe(chosen['details']), chosen['server_name']))
        return chosen

    @staticmethod
    def _version_label(version, current, multiple_servers):
        """'Filme | 4K' - the library says which copy this is, so the old
        'other library' note is not needed any more."""
        parts = [
            version.get('server_name') if multiple_servers else '',
            version.get('library') or '',
        ]

        label = ' · '.join([part for part in parts if part])

        if version is current:
            label = ' - '.join([part for part in
                                [label, i18n_or('Current version', 'Aktuelle Version')]
                                if part])

        return label or describe_file(details) or i18n_or('Unknown', 'Unbekannt')
