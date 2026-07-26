# -*- coding: utf-8 -*-

"""Looks for a better version of the item that is about to be played.

Plex can hold several versions of the same title, either as multiple Media
elements on one item or as a copy on another server that is shared with the
account.  Before playback starts the servers are asked - in parallel and with a
hard time limit - whether they hold the same title, and anything that beats the
version Kodi would have played is offered in a selection dialog.
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

LOG = Logger('quality')

MAX_SERVERS = 8  # servers queried in parallel
MAX_VERSIONS = 12  # versions collected per server
MIN_BITRATE_GAIN = 1.15  # 15% more bitrate before a version counts as better
MIN_BITRATE_DELTA = 1.0  # ... and at least 1 Mbps more

RESOLUTION_RANK = {
    'SD': 1,
    'HD 720': 2,
    'HD 1080': 3,
    '4K': 4,
}

HDR_MARKERS = ('hdr', 'pq', 'hlg', 'smpte2084', 'bt2020')


def resolution_label(value):
    """Map Plex' mixed videoResolution values ('sd', '720', '4k') onto the
    labels used throughout the add-on."""
    try:
        if str(value).lower() == 'sd':
            return 'SD'
        if str(value).lower() == '4k':
            return '4K'
        height = int(value)
    except (TypeError, ValueError):
        return ''

    if height > 1088:
        return '4K'
    if height >= 1080:
        return 'HD 1080'
    if height >= 720:
        return 'HD 720'
    return 'SD'


def media_details(media):
    """Normalised description of a single <Media> element."""
    try:
        bitrate = round(float(media.get('bitrate', 0)) / 1000, 1)
    except (TypeError, ValueError):
        bitrate = 0.0

    try:
        bit_depth = int(media.get('bitDepth', 8) or 8)
    except (TypeError, ValueError):
        bit_depth = 8

    return {
        'bitrate': bitrate,
        'bitDepth': bit_depth,
        'videoResolution': resolution_label(media.get('videoResolution')),
        'container': media.get('container', 'unknown'),
        'codec': media.get('videoCodec'),
        'audioCodec': media.get('audioCodec'),
        'audioChannels': media.get('audioChannels'),
        'hdr': _is_hdr(media),
    }


def _is_hdr(media):
    colour = '%s %s' % (media.get('videoProfile', ''), media.get('colorTrc', ''))
    if any(marker in colour.lower() for marker in HDR_MARKERS):
        return True

    for stream in media.iter('Stream'):
        if stream.get('streamType') != '1':
            continue
        colour = '%s %s %s' % (stream.get('colorTrc', ''), stream.get('DOVIProfile', ''),
                               stream.get('colorPrimaries', ''))
        if any(marker in colour.lower() for marker in HDR_MARKERS):
            return True

    return False


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

    return (
        RESOLUTION_RANK.get(details.get('videoResolution'), 0),
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


def describe(details):
    """Human readable one liner, e.g. '4K HDR - HEVC 10 bit - 24.5 Mbps - MKV'."""
    parts = []

    resolution = details.get('videoResolution')
    if resolution:
        parts.append('%s HDR' % resolution if details.get('hdr') else resolution)
    elif details.get('hdr'):
        parts.append('HDR')

    codec = details.get('codec')
    if codec:
        codec = codec.upper()
        try:
            bit_depth = int(details.get('bitDepth') or 8)
        except (TypeError, ValueError):
            bit_depth = 8
        if bit_depth > 8:
            codec = '%s %s bit' % (codec, bit_depth)
        parts.append(codec)

    audio = details.get('audioCodec')
    if audio:
        channels = str(details.get('audioChannels') or '')
        if channels in ('6', '8'):
            parts.append('%s %d.1' % (audio.upper(), int(channels) - 1))
        else:
            parts.append(audio.upper())

    bitrate = details.get('bitrate')
    if bitrate:
        parts.append('%s Mbps' % bitrate)

    container = details.get('container')
    if container and container != 'unknown':
        parts.append(container.upper())

    return ' - '.join(parts) or i18n_or('Unknown', 'Unbekannt')


class QualitySearch:
    """Collects the playable versions of an item and, when a better one exists,
    lets the user pick which one to play."""

    def __init__(self, context, server, stream, media_id=None):  # pylint: disable=too-many-positional-arguments
        self.context = context
        self.server = server
        self.stream = stream
        self.media_id = media_id

    def run(self):
        """Returns the selected version, or None to play the default one."""
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
        if not (self._guid() or self._title()):
            return []

        servers = [self.server]

        if self.context.settings.quality_search_servers():
            servers += [server for server in self.context.plex_network.get_server_list()
                        if not server.is_offline() and not server.is_secondary()
                        and server.get_uuid() != self.server.get_uuid()]

        return servers[:MAX_SERVERS]

    def _guid(self):
        return self.stream.get('extra', {}).get('guid')

    def _title(self):
        """Only movies are matched by title; episodes are far too ambiguous."""
        full_data = self.stream.get('full_data', {})
        if full_data.get('mediatype') != 'movie':
            return None
        return full_data.get('title')

    def _year(self):
        try:
            return int(self.stream.get('full_data', {}).get('year') or 0)
        except (TypeError, ValueError):
            return 0

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
                  (len(servers), self._guid(), self._title()))

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
        if not found:
            # libraries scanned with different agents do not share a guid, so
            # fall back to the title before giving up on this server
            found = self._by_title(server)

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

        tree = self._talk(server, '/library/all?guid=%s' % quote(guid, safe=''))
        if tree is None:
            return []

        return self._versions_from(server, tree.iter('Video'))

    def _by_title(self, server):
        title = self._title()
        if not title:
            return []

        tree = self._talk(server, '/search?%s' % urlencode({'query': title, 'limit': 30}))
        if tree is None:
            return []

        return self._versions_from(server, self._title_matches(tree))

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

        for video in videos:
            rating_key = video.get('ratingKey')
            if not rating_key or self._is_current_item(server, rating_key):
                continue

            for index, media in enumerate(video.iter('Media')):
                found.append({
                    'part_index': None,  # resolved once the item is loaded
                    'media_index': index,
                    'details': media_details(media),
                    'server_uuid': server.get_uuid(),
                    'server_name': server.get_name(),
                    'media_id': rating_key,
                    'local': False,
                })

            if len(found) >= MAX_VERSIONS:
                break

        return found

    def _is_current_item(self, server, rating_key):
        return (server.get_uuid() == self.server.get_uuid() and
                str(rating_key) == str(self.media_id))

    def _ask(self, candidates, current):
        heading = i18n_or('Better quality available', 'Bessere Qualität verfügbar')
        multiple_servers = len({version['server_uuid'] for version in candidates}) > 1

        items = []
        for version in candidates:
            item = xbmcgui.ListItem(label=describe(version['details']))
            item.setLabel2(self._sub_label(version, current, multiple_servers))
            item.setArt({'icon': CONFIG['icon']})
            items.append(item)

        selected = xbmcgui.Dialog().select(heading, items, useDetails=True, preselect=0)

        # the current version is returned rather than None when the dialog is
        # dismissed, so MediaSelect does not ask about the same versions again
        if selected < 0:
            LOG.debug('Version selection cancelled, keeping the current version')
            return current

        chosen = candidates[selected]
        LOG.debug('Selected version: %s on %s' %
                  (describe(chosen['details']), chosen['server_name']))
        return chosen

    @staticmethod
    def _sub_label(version, current, multiple_servers):
        labels = []

        if multiple_servers:
            labels.append(version['server_name'] or '')

        if version is current:
            labels.append(i18n_or('Current version', 'Aktuelle Version'))
        elif version['server_uuid'] != current['server_uuid']:
            labels.append(i18n_or('Other server', 'Anderer Server'))
        elif str(version['media_id']) != str(current['media_id']):
            labels.append(i18n_or('Other library', 'Andere Bibliothek'))

        return ' - '.join([label for label in labels if label])
