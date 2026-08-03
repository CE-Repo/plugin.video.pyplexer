# -*- coding: utf-8 -*-

"""Resolve localized thumbs, posters and clearlogos with Plex fallback."""

import copy
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.parse import urlencode

import requests
import xbmcvfs  # pylint: disable=import-error

from core.constants import CONFIG
from core.logger import Logger
from plex.http import DIRECT_TIMEOUT
from plex.http import request as http_request
from storage.http_cache import CacheControl

LOG = Logger('artwork')

FANART_API_BASE = 'https://webservice.fanart.tv/v3.2'
TMDB_API_BASE = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/original'
THUMB_ATTRIBUTE = 'pyplexerFanartThumb'
POSTER_ATTRIBUTE = 'pyplexerExternalPoster'
CLEARLOGO_ATTRIBUTE = 'pyplexerExternalClearlogo'
TMDB_BACKGROUNDS_ATTRIBUTE = 'pyplexerExternalTmdbBackgrounds'
ARTWORK_KINDS = ('thumb', 'poster', 'clearlogo')
BACKGROUND_LIMIT = 5
MAX_WORKERS = 4
SYNC_ITEM_LIMIT = 20
BACKGROUND_BATCH_SIZE = 40
GUID_BATCH_SIZE = 40
THUMB_TTL = 7 * 24 * 60 * 60
EMPTY_TTL = 24 * 60 * 60

_GUID_PATTERNS = {
    'tmdb': re.compile(r'(?:tmdb|themoviedb)://([^?&/]+)', re.IGNORECASE),
    'imdb': re.compile(r'imdb://([^?&/]+)', re.IGNORECASE),
    'tvdb': re.compile(r'(?:tvdb|thetvdb)://([^?&/]+)', re.IGNORECASE),
}


def is_configured(settings):
    """Return whether an external artwork provider is configured."""
    return bool(settings.fanart_preferred() and
                (settings.fanart_personal_key() or settings.tmdb_api_key()))


def listing_url_with_guids(settings, url):
    """Ask Plex for provider ids in the original listing response."""
    if (not is_configured(settings) or not str(url).startswith('http') or
            'includeGuids=' in str(url)):
        return url
    separator = '&' if '?' in url else '?'
    return '%s%sincludeGuids=1' % (url, separator)


def clear_cache():
    """Remove cached external artwork hits and misses."""
    CacheControl('fanart_tv', True).delete_cache(True)
    CacheControl('tmdb', True).delete_cache(True)
    return CacheControl('artwork_queue', True).delete_cache(True)


def external_ids(data):
    """Extract all supported provider identifiers from Plex metadata."""
    guids = [guid.get('id') or '' for guid in data.findall('Guid')]
    guids.append(data.get('guid') or '')
    identifiers = {}
    for provider, pattern in _GUID_PATTERNS.items():
        for guid in guids:
            match = pattern.search(guid)
            if match:
                identifiers[provider] = match.group(1)
                break
    return identifiers


def external_id(data, media_type):
    """Extract the identifier required by Fanart.tv from Plex metadata."""
    identifiers = external_ids(data)
    providers = ('tmdb', 'imdb') if media_type == 'movie' else ('tvdb',)
    for provider in providers:
        if identifiers.get(provider):
            return provider, identifiers[provider]
    return None, None


def _has_external_id(data, media_type):
    del media_type
    return bool(external_ids(data))


def _attach_external_guids(server, elements, media_type):
    """Fill omitted Plex Guid children using batched metadata requests."""
    missing = [element for element in elements
               if element.get('ratingKey') and not _has_external_id(element, media_type)]
    if not missing:
        return

    detailed = {}
    excluded = ('Media', 'Genre', 'Country', 'Role', 'Writer', 'Director',
                'Producer', 'Collection', 'Rating', 'Review', 'Chapter',
                'Similar', 'Related', 'Extras', 'Preferences', 'Image',
                'UltraBlurColors', 'Marker')

    for offset in range(0, len(missing), GUID_BATCH_SIZE):
        batch = missing[offset:offset + GUID_BATCH_SIZE]
        query = urlencode({
            'includeGuids': '1',
            'excludeElements': ','.join(excluded),
            'excludeFields': 'summary,tagline',
        })
        path = '/library/metadata/%s?%s' % (
            ','.join([element.get('ratingKey') for element in batch]), query)
        try:
            tree = server.processed_xml(path)
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('Plex GUID lookup failed: %s' % error)
            continue

        if tree is None:
            continue
        for node in tree.iter():
            rating_key = node.get('ratingKey')
            if rating_key and node.findall('Guid'):
                detailed[str(rating_key)] = node

    for element in missing:
        detail = detailed.get(str(element.get('ratingKey')))
        if detail is None:
            continue
        for guid in detail.findall('Guid'):
            element.append(copy.copy(guid))


def _language(settings):
    value = str(settings.fanart_language() or '').strip().lower()
    if not value or value == 'auto':
        value = str(CONFIG.get('language') or 'en').strip().lower()
    return value.replace('_', '-').split('-', 1)[0]


def _likes(image):
    try:
        return int(image.get('likes') or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def select_thumb(images, language):
    """Choose the most-liked Fanart.tv thumb in exactly one language."""
    language = str(language or '').lower()
    images = [image for image in (images or [])
              if (isinstance(image, dict) and image.get('url') and
                  str(image.get('lang') or '').lower() == language)]
    if not images:
        return ''

    def sort_key(image):
        return -_likes(image), str(image.get('id') or '')

    return min(images, key=sort_key).get('url') or ''


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def select_tmdb_thumb(images, language):
    """Choose the best-rated TMDb backdrop in exactly one language."""
    language = str(language or '').lower()
    images = [image for image in (images or [])
              if (isinstance(image, dict) and image.get('file_path') and
                  str(image.get('iso_639_1') or '').lower() == language)]
    if not images:
        return ''

    def sort_key(image):
        pixels = _number(image.get('width')) * _number(image.get('height'))
        return (-_number(image.get('vote_average')),
                -_number(image.get('vote_count')),
                -pixels,
                str(image.get('file_path') or ''))

    path = min(images, key=sort_key).get('file_path') or ''
    return TMDB_IMAGE_BASE + path if path else ''


def select_tmdb_wallpapers(images):
    """Return the five best-rated language-neutral TMDb backdrops."""
    images = [image for image in (images or [])
              if isinstance(image, dict) and image.get('file_path') and
              (image.get('iso_639_1') is None or
               str(image.get('iso_639_1') or '').lower() in ('', '00'))]

    def sort_key(image):
        pixels = _number(image.get('width')) * _number(image.get('height'))
        return (-_number(image.get('vote_average')),
                -_number(image.get('vote_count')),
                -pixels,
                str(image.get('file_path') or ''))

    urls = []
    for image in sorted(images, key=sort_key):
        url = TMDB_IMAGE_BASE + (image.get('file_path') or '')
        if url not in urls:
            urls.append(url)
    return urls[:BACKGROUND_LIMIT]


def select_tmdb_clearlogo(images, language):
    """Choose the best-rated TMDb clearlogo in exactly one language."""
    return select_tmdb_thumb(images, language)


def select_tmdb_poster(images, language):
    """Choose the best-rated TMDb poster in exactly one language."""
    return select_tmdb_thumb(images, language)


def _empty_artwork():
    return {
        'thumb': ('', ''),
        'poster': ('', ''),
        'clearlogo': ('', ''),
        'background': ([], []),
    }


def external_tmdb_backgrounds(data):
    """Read resolved TMDb backgrounds from a Plex XML node."""
    value = data.get(TMDB_BACKGROUNDS_ATTRIBUTE) if data is not None else ''
    if not value:
        return []
    try:
        backgrounds = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(backgrounds, list):
        return []
    return [url for url in backgrounds[:BACKGROUND_LIMIT]
            if isinstance(url, str) and url.startswith(('http://', 'https://'))]


class FanartTvClient:
    """Small cached client used while a Kodi directory is being assembled."""

    def __init__(self, settings):
        self.settings = settings
        self.personal_key = str(settings.fanart_personal_key() or '').strip()
        self.preferred_language = _language(settings)
        self.credential_namespace = hashlib.sha256(
            self.personal_key.encode('utf-8')).hexdigest()[:12]
        self.cache = CacheControl('fanart_tv', True)
        # One broken external service must not turn a large Plex library into
        # hundreds of sequential failures. The breaker lives for this listing.
        self.disabled = threading.Event()

    def _headers(self):
        return {
            'Accept': 'application/json',
            'client-key': self.personal_key,
        }

    def _cache_name(self, media_type, identifier):
        return self.cache.sha512_cache_name(
            'fanart_tv_artwork_v5', media_type, '%s:%s:%s' %
            (identifier, self.preferred_language, self.credential_namespace))

    def _cached(self, cache_name):
        found, value = self.cache.read_cache(cache_name)
        if not found or not isinstance(value, dict):
            return False, _empty_artwork()
        try:
            if float(value.get('expires', 0)) <= time.time():
                return False, _empty_artwork()
        except (TypeError, ValueError):
            return False, _empty_artwork()
        return True, {
            'thumb': tuple(value.get('thumb') or ('', '')),
            'poster': tuple(value.get('poster') or ('', '')),
            'clearlogo': tuple(value.get('clearlogo') or ('', '')),
            # Fanart.tv is intentionally not used for backgrounds.
            'background': ([], []),
        }

    def cached_artwork(self, media_type, provider, identifier):
        """Read artwork without contacting Fanart.tv."""
        if not identifier or (media_type == 'show' and provider != 'tvdb'):
            return True, _empty_artwork()
        return self._cached(self._cache_name(media_type, identifier))

    def _store(self, cache_name, artwork):
        available = any(url for values in artwork.values() for url in values)
        ttl = THUMB_TTL if available else EMPTY_TTL
        self.cache.write_cache(cache_name, {
            'expires': time.time() + ttl,
            'thumb': artwork['thumb'],
            'poster': artwork['poster'],
            'clearlogo': artwork['clearlogo'],
            'background': ([], []),
        })

    def artwork(self, media_type, provider, identifier):
        """Return localized Fanart.tv thumbs, posters and clearlogos."""
        if not identifier or self.disabled.is_set():
            return _empty_artwork()

        cache_name = self._cache_name(media_type, identifier)
        found, artwork = self._cached(cache_name)
        if found:
            return artwork

        resource = 'movies' if media_type == 'movie' else 'tv'
        # The movie endpoint accepts TMDb and IMDb ids. TV requires TVDb.
        if media_type == 'show' and provider != 'tvdb':
            return _empty_artwork()
        url = '%s/%s/%s' % (FANART_API_BASE, resource, identifier)

        try:
            response = http_request('get', url, headers=self._headers(),
                                    verify=True, timeout=DIRECT_TIMEOUT)
        except requests.exceptions.RequestException as error:
            self.disabled.set()
            LOG.debug('Fanart.tv request failed for %s %s: %s' %
                      (media_type, identifier, error))
            return _empty_artwork()

        if response.status_code == requests.codes.not_found:  # pylint: disable=no-member
            artwork = _empty_artwork()
            self._store(cache_name, artwork)
            return artwork
        if response.status_code != requests.codes.ok:  # pylint: disable=no-member
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                self.disabled.set()
            LOG.debug('Fanart.tv HTTP %s for %s %s' %
                      (response.status_code, media_type, identifier))
            return _empty_artwork()

        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            self.disabled.set()
            LOG.debug('Invalid Fanart.tv response for %s %s: %s' %
                      (media_type, identifier, error))
            return _empty_artwork()
        if not isinstance(payload, dict):
            self.disabled.set()
            LOG.debug('Unexpected Fanart.tv response for %s %s' %
                      (media_type, identifier))
            return _empty_artwork()

        thumb_key = 'moviethumb' if media_type == 'movie' else 'tvthumb'
        poster_key = 'movieposter' if media_type == 'movie' else 'tvposter'
        logo_keys = (('hdmovielogo', 'movielogo') if media_type == 'movie'
                     else ('hdtvlogo', 'tvlogo'))
        logos = []
        for logo_key in logo_keys:
            logos.extend(payload.get(logo_key) or [])
        artwork = {
            'thumb': (
                select_thumb(payload.get(thumb_key), self.preferred_language),
                select_thumb(payload.get(thumb_key), 'en')),
            'poster': (
                select_thumb(payload.get(poster_key), self.preferred_language),
                select_thumb(payload.get(poster_key), 'en')),
            'clearlogo': (
                select_thumb(logos, self.preferred_language),
                select_thumb(logos, 'en')),
            'background': ([], []),
        }
        self._store(cache_name, artwork)
        return artwork


class TmdbClient:
    """Cached TMDb client for optional localized artwork fallbacks."""

    def __init__(self, settings):
        self.api_key = str(settings.tmdb_api_key() or '').strip()
        self.preferred_language = _language(settings)
        self.credential_namespace = hashlib.sha256(
            self.api_key.encode('utf-8')).hexdigest()[:12]
        self.cache = CacheControl('tmdb', True)
        self.disabled = threading.Event()

    def _authentication(self, params):
        headers = {'Accept': 'application/json'}
        params = dict(params or {})
        if re.fullmatch(r'[0-9a-fA-F]{32}', self.api_key):
            params['api_key'] = self.api_key
        else:
            headers['Authorization'] = 'Bearer %s' % self.api_key
        return headers, params

    def _request_json(self, path, params=None):
        if not self.api_key or self.disabled.is_set():
            return False, None
        headers, params = self._authentication(params)
        try:
            response = http_request(
                'get', TMDB_API_BASE + path, headers=headers, params=params,
                verify=True, timeout=DIRECT_TIMEOUT)
        except requests.exceptions.RequestException as error:
            self.disabled.set()
            LOG.debug('TMDb request failed for %s: %s' % (path, error))
            return False, None

        if response.status_code == requests.codes.not_found:  # pylint: disable=no-member
            return True, {}
        if response.status_code != requests.codes.ok:  # pylint: disable=no-member
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                self.disabled.set()
            LOG.debug('TMDb HTTP %s for %s' % (response.status_code, path))
            return False, None
        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            self.disabled.set()
            LOG.debug('Invalid TMDb response for %s: %s' % (path, error))
            return False, None
        if not isinstance(payload, dict):
            self.disabled.set()
            LOG.debug('Unexpected TMDb response for %s' % path)
            return False, None
        return True, payload

    def _cache_name(self, media_type, identifiers):
        identity = '|'.join('%s:%s' % (key, identifiers[key])
                            for key in sorted(identifiers))
        return self.cache.sha512_cache_name(
            'tmdb_artwork_v7', media_type, '%s:%s:%s' %
            (identity, self.preferred_language, self.credential_namespace))

    def _cached(self, cache_name):
        found, value = self.cache.read_cache(cache_name)
        if not found or not isinstance(value, dict):
            return False, _empty_artwork()
        try:
            if float(value.get('expires', 0)) <= time.time():
                return False, _empty_artwork()
        except (TypeError, ValueError):
            return False, _empty_artwork()
        return True, {
            'thumb': tuple(value.get('thumb') or ('', '')),
            'poster': tuple(value.get('poster') or ('', '')),
            'clearlogo': tuple(value.get('clearlogo') or ('', '')),
            'background': tuple(value.get('background') or ([], [])),
        }

    def cached_artwork(self, media_type, identifiers):
        """Read artwork without contacting TMDb."""
        if not identifiers:
            return True, _empty_artwork()
        return self._cached(self._cache_name(media_type, identifiers))

    def _store(self, cache_name, artwork):
        available = any(url for values in artwork.values() for url in values)
        ttl = THUMB_TTL if available else EMPTY_TTL
        self.cache.write_cache(cache_name, {
            'expires': time.time() + ttl,
            'thumb': artwork['thumb'],
            'poster': artwork['poster'],
            'clearlogo': artwork['clearlogo'],
            'background': artwork['background'],
        })

    def _resolve_id(self, media_type, identifiers):
        if identifiers.get('tmdb'):
            return True, identifiers['tmdb']

        sources = ('imdb', 'tvdb') if media_type == 'show' else ('imdb',)
        result_key = 'tv_results' if media_type == 'show' else 'movie_results'
        for source in sources:
            identifier = identifiers.get(source)
            if not identifier:
                continue
            success, payload = self._request_json(
                '/find/%s' % quote(str(identifier), safe=''),
                {'external_source': '%s_id' % source})
            if not success:
                return False, ''
            results = payload.get(result_key) or []
            if results and isinstance(results[0], dict) and results[0].get('id'):
                return True, str(results[0]['id'])
        return True, ''

    def artwork(self, media_type, identifiers):
        """Return localized TMDb backdrops, posters and clearlogos."""
        if not identifiers or self.disabled.is_set():
            return _empty_artwork()

        cache_name = self._cache_name(media_type, identifiers)
        found, artwork = self._cached(cache_name)
        if found:
            return artwork

        success, tmdb_id = self._resolve_id(media_type, identifiers)
        if not success:
            return _empty_artwork()
        if not tmdb_id:
            artwork = _empty_artwork()
            self._store(cache_name, artwork)
            return artwork

        resource = 'movie' if media_type == 'movie' else 'tv'
        success, payload = self._request_json(
            '/%s/%s/images' % (resource, quote(str(tmdb_id), safe='')),
            {'language': self.preferred_language,
             'include_image_language': 'en,null'})
        if not success:
            return _empty_artwork()
        artwork = {
            'thumb': (
                select_tmdb_thumb(payload.get('backdrops'),
                                  self.preferred_language),
                select_tmdb_thumb(payload.get('backdrops'), 'en')),
            'poster': (
                select_tmdb_poster(payload.get('posters'),
                                   self.preferred_language),
                select_tmdb_poster(payload.get('posters'), 'en')),
            'clearlogo': (
                select_tmdb_clearlogo(payload.get('logos'),
                                      self.preferred_language),
                select_tmdb_clearlogo(payload.get('logos'), 'en')),
            'background': (
                select_tmdb_wallpapers(payload.get('backdrops')), []),
        }
        self._store(cache_name, artwork)
        return artwork


def _fanart_identity(media_type, identifiers):
    providers = ('tmdb', 'imdb') if media_type == 'movie' else ('tvdb',)
    provider = next((name for name in providers if identifiers.get(name)), None)
    return provider, identifiers.get(provider) if provider else ''


def _choose_artwork(fanart_artwork, tmdb_artwork):
    selected = {}
    for kind in ARTWORK_KINDS:
        fanart_preferred, fanart_english = fanart_artwork[kind]
        tmdb_preferred, tmdb_english = tmdb_artwork[kind]
        selected[kind] = (fanart_preferred or fanart_english or
                          tmdb_preferred or tmdb_english or '')
    tmdb_wallpapers, _ = tmdb_artwork['background']
    selected['background'] = list(tmdb_wallpapers)[:BACKGROUND_LIMIT]
    return selected


def _fetch_external_artwork(fanart_client, tmdb_client, media_type,
                            identifiers):
    """Resolve and cache one title without letting either API break a list."""
    fanart_artwork = _empty_artwork()
    tmdb_artwork = _empty_artwork()
    provider, identifier = _fanart_identity(media_type, identifiers)

    if fanart_client is not None and identifier:
        try:
            fanart_artwork = fanart_client.artwork(
                media_type, provider, identifier)
        except Exception as error:  # pylint: disable=broad-except
            fanart_client.disabled.set()
            LOG.debug('Unexpected Fanart.tv error for %s %s: %s' %
                      (media_type, identifier, error))

    # TMDb is always consulted when configured because it is the sole
    # external source for fanart backgrounds.
    if tmdb_client is not None:
        try:
            tmdb_artwork = tmdb_client.artwork(media_type, identifiers)
        except Exception as error:  # pylint: disable=broad-except
            tmdb_client.disabled.set()
            LOG.debug('Unexpected TMDb error for %s: %s' %
                      (media_type, error))

    return _choose_artwork(fanart_artwork, tmdb_artwork)


def _cached_external_artwork(fanart_client, tmdb_client, media_type,
                             identifiers):
    """Resolve one title from cache and report whether background work remains."""
    fanart_artwork = _empty_artwork()
    tmdb_artwork = _empty_artwork()
    provider, identifier = _fanart_identity(media_type, identifiers)

    if fanart_client is not None and identifier:
        found, fanart_artwork = fanart_client.cached_artwork(
            media_type, provider, identifier)
        if not found:
            # A lower-priority provider cannot be shown until Fanart.tv's
            # preferred/English result is known.
            return _choose_artwork(_empty_artwork(), _empty_artwork()), False

    if tmdb_client is not None:
        found, tmdb_artwork = tmdb_client.cached_artwork(
            media_type, identifiers)
        if not found:
            return _choose_artwork(fanart_artwork, _empty_artwork()), False

    return _choose_artwork(fanart_artwork, tmdb_artwork), True


class ArtworkQueue:
    """Persistent, de-duplicated jobs consumed by PyPlexer's service."""

    def __init__(self):
        self.cache = CacheControl('artwork_queue', True)

    @staticmethod
    def _identity(identifiers):
        return '|'.join('%s:%s' % (key, identifiers[key])
                        for key in sorted(identifiers))

    def enqueue(self, media_type, identifiers):
        if self.cache.cache_location is None:
            return False
        name = self.cache.sha512_cache_name(
            'artwork_job', media_type, self._identity(identifiers))
        path = self.cache.cache_location + name
        if xbmcvfs.exists(path):
            return True
        return self.cache.write_cache(name, {
            'media_type': media_type,
            'identifiers': dict(identifiers),
        })

    def jobs(self, limit=BACKGROUND_BATCH_SIZE):
        if self.cache.cache_location is None:
            return []
        _, files = xbmcvfs.listdir(self.cache.cache_location)
        jobs = []
        for name in files:
            if not name.endswith('.cache'):
                continue
            found, job = self.cache.read_cache(name)
            if (found and isinstance(job, dict) and
                    job.get('media_type') in ('movie', 'show') and
                    isinstance(job.get('identifiers'), dict)):
                jobs.append((name, job))
            else:
                self.remove(name)
            if len(jobs) >= limit:
                break
        return jobs

    def remove(self, name):
        if self.cache.cache_location is None:
            return False
        return xbmcvfs.delete(self.cache.cache_location + name)


def process_artwork_queue(settings, limit=BACKGROUND_BATCH_SIZE):
    """Warm artwork caches in the background service, one bounded batch."""
    queue = ArtworkQueue()
    jobs = queue.jobs(limit)
    if not jobs:
        return 0
    if not is_configured(settings):
        queue.cache.delete_cache(True)
        return 0

    fanart_client = (FanartTvClient(settings)
                     if settings.fanart_personal_key() else None)
    tmdb_client = TmdbClient(settings) if settings.tmdb_api_key() else None

    def process(job_entry):
        name, job = job_entry
        _fetch_external_artwork(
            fanart_client, tmdb_client, job['media_type'], job['identifiers'])
        return name

    completed = 0
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(jobs))) as executor:
        for name in executor.map(process, jobs):
            queue.remove(name)
            completed += 1
    return completed


def artwork_queue_pending():
    """Return whether the background service still has artwork to fetch."""
    return bool(ArtworkQueue().jobs(limit=1))


def prefer_artwork(context, elements, media_type, server=None):
    """Resolve localized artwork and TMDb-only fanart backgrounds."""
    elements = list(elements)
    if not elements or media_type not in ('movie', 'show'):
        return
    if not is_configured(context.settings):
        return

    if server is not None:
        _attach_external_guids(server, elements, media_type)

    identified = []
    for element in elements:
        identifiers = external_ids(element)
        if identifiers:
            identified.append((element, identifiers))

    if not identified:
        LOG.debug('No external artwork ids found for %s items' % media_type)
        return

    fanart_client = (FanartTvClient(context.settings)
                     if context.settings.fanart_personal_key() else None)
    tmdb_client = (TmdbClient(context.settings)
                   if context.settings.tmdb_api_key() else None)
    unique = {}
    for _, identifiers in identified:
        identity = tuple(sorted(identifiers.items()))
        unique[identity] = ('', '', '', [])

    if len(unique) > SYNC_ITEM_LIMIT:
        queue = ArtworkQueue()
        queued = 0
        for identity in unique:
            identifiers = dict(identity)
            artwork, complete = _cached_external_artwork(
                fanart_client, tmdb_client, media_type, identifiers)
            unique[identity] = (artwork['thumb'], artwork['poster'],
                                artwork['clearlogo'], artwork['background'])
            if not complete and queue.enqueue(media_type, identifiers):
                queued += 1
        LOG.debug('Large %s list: cache-only artwork, %s job(s) queued' %
                  (media_type, queued))
    else:
        def fetch(identity):
            artwork = _fetch_external_artwork(
                fanart_client, tmdb_client, media_type, dict(identity))
            return identity, (artwork['thumb'], artwork['poster'],
                              artwork['clearlogo'], artwork['background'])

        workers = min(MAX_WORKERS, len(unique))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for key, artwork in executor.map(fetch, unique):
                unique[key] = artwork

    thumbs_applied = 0
    posters_applied = 0
    logos_applied = 0
    backgrounds_applied = 0
    for element, identifiers in identified:
        identity = tuple(sorted(identifiers.items()))
        thumb, poster, clearlogo, backgrounds = unique.get(
            identity, ('', '', '', []))
        if thumb:
            element.set(THUMB_ATTRIBUTE, thumb)
            thumbs_applied += 1
        if poster:
            element.set(POSTER_ATTRIBUTE, poster)
            posters_applied += 1
        if clearlogo:
            element.set(CLEARLOGO_ATTRIBUTE, clearlogo)
            logos_applied += 1
        if backgrounds:
            element.set(TMDB_BACKGROUNDS_ATTRIBUTE, json.dumps(
                backgrounds, separators=(',', ':')))
            backgrounds_applied += 1

    LOG.debug('External thumbs/posters/logos/TMDb backgrounds applied to '
              '%s/%s/%s/%s of %s %s item(s)' %
              (thumbs_applied, posters_applied, logos_applied,
               backgrounds_applied, len(elements), media_type))


def prefer_thumbs(context, elements, media_type, server=None):
    """Backward-compatible alias for the external artwork resolver."""
    return prefer_artwork(context, elements, media_type, server)
