# -*- coding: utf-8 -*-

"""Resolve localized landscape thumbs with Plex artwork as the fallback."""

import copy
import hashlib
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.parse import urlencode

import requests

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
MAX_WORKERS = 4
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


def clear_cache():
    """Remove cached external artwork hits and misses."""
    CacheControl('fanart_tv', True).delete_cache(True)
    return CacheControl('tmdb', True).delete_cache(True)


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
            'fanart_tv_thumb_v3', media_type, '%s:%s:%s' %
            (identifier, self.preferred_language, self.credential_namespace))

    def _cached(self, cache_name):
        found, value = self.cache.read_cache(cache_name)
        if not found or not isinstance(value, dict):
            return False, ('', '')
        try:
            if float(value.get('expires', 0)) <= time.time():
                return False, ('', '')
        except (TypeError, ValueError):
            return False, ('', '')
        return True, (value.get('preferred') or '', value.get('english') or '')

    def _store(self, cache_name, preferred, english):
        ttl = THUMB_TTL if preferred or english else EMPTY_TTL
        self.cache.write_cache(cache_name, {
            'expires': time.time() + ttl,
            'preferred': preferred,
            'english': english,
        })

    def thumbs(self, media_type, provider, identifier):
        """Return preferred and English Fanart.tv thumb URLs independently."""
        if not identifier or self.disabled.is_set():
            return '', ''

        cache_name = self._cache_name(media_type, identifier)
        found, thumbs = self._cached(cache_name)
        if found:
            return thumbs

        resource = 'movies' if media_type == 'movie' else 'tv'
        # The movie endpoint accepts TMDb and IMDb ids. TV requires TVDb.
        if media_type == 'show' and provider != 'tvdb':
            return '', ''
        url = '%s/%s/%s' % (FANART_API_BASE, resource, identifier)

        try:
            response = http_request('get', url, headers=self._headers(),
                                    verify=True, timeout=DIRECT_TIMEOUT)
        except requests.exceptions.RequestException as error:
            self.disabled.set()
            LOG.debug('Thumb request failed for %s %s: %s' %
                      (media_type, identifier, error))
            return '', ''

        if response.status_code == requests.codes.not_found:  # pylint: disable=no-member
            self._store(cache_name, '', '')
            return '', ''
        if response.status_code != requests.codes.ok:  # pylint: disable=no-member
            if response.status_code in (401, 403, 429) or response.status_code >= 500:
                self.disabled.set()
            LOG.debug('Fanart.tv HTTP %s for %s %s' %
                      (response.status_code, media_type, identifier))
            return '', ''

        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            self.disabled.set()
            LOG.debug('Invalid Fanart.tv response for %s %s: %s' %
                      (media_type, identifier, error))
            return '', ''
        if not isinstance(payload, dict):
            self.disabled.set()
            LOG.debug('Unexpected Fanart.tv response for %s %s' %
                      (media_type, identifier))
            return '', ''

        key = 'moviethumb' if media_type == 'movie' else 'tvthumb'
        preferred = select_thumb(payload.get(key), self.preferred_language)
        english = select_thumb(payload.get(key), 'en')
        self._store(cache_name, preferred, english)
        return preferred, english


class TmdbClient:
    """Cached TMDb client for the optional localized-backdrop fallback."""

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
            'tmdb_thumb_v2', media_type, '%s:%s:%s' %
            (identity, self.preferred_language, self.credential_namespace))

    def _cached(self, cache_name):
        found, value = self.cache.read_cache(cache_name)
        if not found or not isinstance(value, dict):
            return False, ('', '')
        try:
            if float(value.get('expires', 0)) <= time.time():
                return False, ('', '')
        except (TypeError, ValueError):
            return False, ('', '')
        return True, (value.get('preferred') or '', value.get('english') or '')

    def _store(self, cache_name, preferred, english):
        ttl = THUMB_TTL if preferred or english else EMPTY_TTL
        self.cache.write_cache(cache_name, {
            'expires': time.time() + ttl,
            'preferred': preferred,
            'english': english,
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

    def thumbs(self, media_type, identifiers):
        """Return preferred and English TMDb backdrops independently."""
        if not identifiers or self.disabled.is_set():
            return '', ''

        cache_name = self._cache_name(media_type, identifiers)
        found, thumbs = self._cached(cache_name)
        if found:
            return thumbs

        success, tmdb_id = self._resolve_id(media_type, identifiers)
        if not success:
            return '', ''
        if not tmdb_id:
            self._store(cache_name, '', '')
            return '', ''

        resource = 'movie' if media_type == 'movie' else 'tv'
        success, payload = self._request_json(
            '/%s/%s/images' % (resource, quote(str(tmdb_id), safe='')),
            {'language': self.preferred_language,
             'include_image_language': 'en'})
        if not success:
            return '', ''
        preferred = select_tmdb_thumb(payload.get('backdrops'),
                                      self.preferred_language)
        english = select_tmdb_thumb(payload.get('backdrops'), 'en')
        self._store(cache_name, preferred, english)
        return preferred, english


def prefer_thumbs(context, elements, media_type, server=None):
    """Apply localized/English Fanart, localized/English TMDb, then Plex."""
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
        unique[identity] = None

    def fetch(identity):
        identifiers = dict(identity)
        preferred = ''
        english = ''

        if fanart_client is not None:
            providers = ('tmdb', 'imdb') if media_type == 'movie' else ('tvdb',)
            provider = next((name for name in providers
                             if identifiers.get(name)), None)
            identifier = identifiers.get(provider) if provider else ''
            if identifier:
                try:
                    preferred, english = fanart_client.thumbs(
                        media_type, provider, identifier)
                except Exception as error:  # pylint: disable=broad-except
                    fanart_client.disabled.set()
                    LOG.debug('Unexpected Fanart.tv error for %s %s: %s' %
                              (media_type, identifier, error))

        if preferred:
            return identity, preferred
        if english:
            return identity, english

        if tmdb_client is not None:
            try:
                tmdb_preferred, tmdb_english = tmdb_client.thumbs(
                    media_type, identifiers)
            except Exception as error:  # pylint: disable=broad-except
                tmdb_client.disabled.set()
                LOG.debug('Unexpected TMDb error for %s: %s' %
                          (media_type, error))
                tmdb_preferred = ''
                tmdb_english = ''
            if tmdb_preferred:
                return identity, tmdb_preferred
            if tmdb_english:
                return identity, tmdb_english

        return identity, ''

    workers = min(MAX_WORKERS, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for key, thumb in executor.map(fetch, unique):
            unique[key] = thumb

    applied = 0
    for element, identifiers in identified:
        thumb = unique.get(tuple(sorted(identifiers.items()))) or ''
        if thumb:
            element.set(THUMB_ATTRIBUTE, thumb)
            applied += 1

    LOG.debug('External thumbs applied to %s of %s %s item(s)' %
              (applied, len(elements), media_type))
