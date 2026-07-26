# -*- coding: utf-8 -*-

"""Search across the servers of the account.

Two callers use this: the add-on's own search, which wants everything Plex can
find, and players such as TMDb Helper, which hand over a title they have
already identified and expect exactly one item back.  The second kind passes
``year`` for a movie, or ``showtitle``/``season``/``episode`` for an episode,
and gets a precise lookup instead of Plex' fuzzy full text search.
"""

import xml.etree.ElementTree as ETree
from urllib.parse import quote

import xbmc  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.logger import Logger
from core.strings import decode_utf8
from core.strings import i18n
from gui.builders.episode import create_episode_item
from gui.builders.movie import create_movie_item
from playback.quality import media_details
from playback.quality import normalise_title
from playback.quality import quality_score
from plex.network import Plex

LOG = Logger()

YEAR_TOLERANCE = 1  # the same film is released a year apart in some regions


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    params = context.params
    for param in ['video_type']:  # check for expected parameters
        if param not in params:
            return

    if not params.get('query'):
        params['query'] = _get_search_query()

    # keep the term as typed; params['query'] is escaped for the Plex URL
    params['title'] = params.get('title') or params.get('query', '')
    params['query'] = _quote(params['query'])

    if _is_precise(params):
        # the caller knows what it wants, so the server name must not end up
        # in the title where it would spoil the match
        params['no_server_prefix'] = True

    context.params = params

    succeeded = False
    search_results = search(context)
    log_results = list(map(lambda x: decode_utf8(ETree.tostring(x[1])), search_results))
    LOG.debug('Found search results: %s' % '\n\n'.join(log_results))

    if search_results:
        LOG.debug('Found a server with the requested content %s' % params['query'])

        items = []
        append_item = items.append
        url = ''

        for server_uuid, tree, search_result in search_results:
            server = context.plex_network.get_server_from_uuid(server_uuid)
            if context.params.get('video_type') == 'movie':
                item = Item(server, url, tree, search_result)
                append_item(create_movie_item(context, item))

            elif context.params.get('video_type') == 'episode':
                item = Item(server, url, tree, search_result)
                append_item(create_episode_item(context, item))

        if items:
            xbmcplugin.addDirectoryItems(get_handle(), items, len(items))
            succeeded = True
            if context.params.get('video_type') == 'movie':
                xbmcplugin.setContent(get_handle(), 'movies')
            elif context.params.get('video_type') == 'episode':
                xbmcplugin.setContent(get_handle(), 'episodes')
    else:
        LOG.debug('Content not found on any server')

    xbmcplugin.endOfDirectory(get_handle(), succeeded=succeeded,
                              cacheToDisc=context.settings.cache_directory())


def search(context):
    episode = _episode_wanted(context.params)
    if episode:
        results = _search_episode(context, episode)
        if results:
            return _sort_results(context, results)

        LOG.debug('No exact episode match, falling back to the plain search')

    results = _search_sections(context)

    # only a caller that named a year gets the strict treatment; the keyboard
    # search has to stay broad, it is a search after all
    if context.params.get('video_type') == 'movie' and _is_precise(context.params):
        results = _refine_movies(context, results)

    return _sort_results(context, results)


def _search_sections(context):
    """Plex' full text search, one call per matching library section."""
    results = []

    content_type = _get_content_type(context.params.get('video_type'))
    search_type = _get_search_type(context.params.get('video_type'))
    if not content_type or not search_type:
        return []

    server_list = context.plex_network.get_server_list()
    params = context.params

    for server in server_list:
        processed_xml = server.processed_xml

        sections = server.get_sections()
        for section in sections:

            if section.get_type() == content_type:
                query = params.get('query')
                url = '%s/search?type=%s&query=%s' % (section.get_path(), search_type, query)
                processed = processed_xml(url)

                if _is_not_none(processed):
                    results += _get_search_results(server, processed)

    return results


def _refine_movies(context, results):
    """Keep the film the caller asked for and nothing else.  Plex answers
    'Speak No Evil' with every film of that name, so the title has to match
    exactly and the year has to fit; a film of the same name from another year
    is a different film and is dropped, even when that leaves nothing.

    The year is only allowed to differ by one, and only when no item carries
    the requested year, because regions release a film a year apart.
    """
    wanted = _wanted_titles(context.params)
    if not wanted:
        return results

    year = _as_int(context.params.get('year'))

    exact = []
    close = []

    for entry in results:
        if not _title_matches(entry[2], wanted):
            continue

        if not year:
            exact.append(entry)
            continue

        found = _as_int(entry[2].get('year'))
        if found == year:
            exact.append(entry)
        elif found and abs(found - year) <= YEAR_TOLERANCE:
            close.append(entry)

    matches = exact or close
    if not matches:
        LOG.debug('No item matches %s (%s), the caller gets nothing rather than '
                  'the wrong film' % (wanted, year))

    return _deduplicate(matches)


def _search_episode(context, wanted):
    """Find the show by title, then the episode by its numbers - episode titles
    differ too much between libraries to search for them."""
    show, season, episode = wanted
    query = _quote(show)
    normalised = normalise_title(show)

    results = []

    for server in context.plex_network.get_server_list():
        for section in server.get_sections():
            if section.get_type() != 'show':
                continue

            found = server.processed_xml('%s/search?type=2&query=%s' %
                                         (section.get_path(), query))
            if not _is_not_none(found):
                continue

            for directory in found.iter('Directory'):
                if directory.get('type') != 'show':
                    continue
                if not _title_matches(directory, normalised):
                    continue

                rating_key = directory.get('ratingKey')
                if not rating_key:
                    continue

                leaves = server.processed_xml('/library/metadata/%s/allLeaves' % rating_key)
                if not _is_not_none(leaves):
                    continue

                for video in leaves.iter('Video'):
                    if (_as_int(video.get('parentIndex')) == season and
                            _as_int(video.get('index')) == episode):
                        results.append((server.get_uuid(), leaves, video))

    return _deduplicate(results)


def _wanted_titles(params):
    """The caller may know the title in another language than the library."""
    titles = {normalise_title(params.get('title')),
              normalise_title(params.get('originaltitle'))}
    titles.discard('')
    return titles


def _sort_results(context, results):
    """Newest first, with the closest match on top: what the caller asked for
    should not sit below a namesake from twenty years ago."""
    if context.params.get('video_type') == 'episode':
        return sorted(results, key=_episode_order)

    wanted = _wanted_titles(context.params)
    year = _as_int(context.params.get('year'))

    return sorted(results, key=lambda entry: _movie_order(entry[2], wanted, year))


def _movie_order(element, wanted, year):
    found = _as_int(element.get('year')) or 0

    if not year:
        distance = 0  # nothing to compare against, order by year alone
    elif found:
        distance = abs(found - year)
    else:
        distance = 9999  # an item without a year is no match for one

    return (
        0 if wanted and _title_matches(element, wanted) else 1,
        distance,
        -found,
        normalise_title(element.get('title')),
    )


def _episode_order(entry):
    element = entry[2]

    return (
        normalise_title(element.get('grandparentTitle')),
        _as_int(element.get('parentIndex')) or 0,
        _as_int(element.get('index')) or 0,
    )


def _deduplicate(results):
    """One entry per title: the same film on two servers, or in a 4K library
    next to a Full HD one, is the same choice for the caller - offer the best
    copy and let the playback quality search present the rest."""
    best = {}
    order = []

    for entry in results:
        element = entry[2]
        key = element.get('guid') or '%s|%s|%s|%s' % (normalise_title(element.get('title')),
                                                      element.get('year'),
                                                      element.get('parentIndex'),
                                                      element.get('index'))

        if key not in best:
            best[key] = entry
            order.append(key)
            continue

        if _best_media_score(element) > _best_media_score(best[key][2]):
            best[key] = entry

    return [best[key] for key in order]


def _best_media_score(element):
    scores = [quality_score(media_details(media)) for media in element.iter('Media')]
    return max(scores) if scores else ()


def _title_matches(element, wanted):
    """Libraries hold the localised title, callers may know the original one,
    so either side is allowed to carry several spellings."""
    if isinstance(wanted, str):
        wanted = {wanted}

    candidates = (element.get('title'), element.get('originalTitle'),
                  element.get('titleSort'))
    return any(normalise_title(candidate) in wanted for candidate in candidates if candidate)


def _episode_wanted(params):
    if params.get('video_type') != 'episode':
        return None

    show = params.get('showtitle')
    season = _as_int(params.get('season'))
    episode = _as_int(params.get('episode'))

    if not show or season is None or episode is None:
        return None

    return show, season, episode


def _is_precise(params):
    return bool(params.get('year') or _episode_wanted(params))


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_search_query():
    text = ''
    keyboard = xbmc.Keyboard('', i18n('Search...'))
    keyboard.setHeading(i18n('Enter search term'))
    keyboard.doModal()
    if keyboard.isConfirmed():
        text = keyboard.getText()
        if not text.strip():
            return ''
    LOG.debug('Search term input: %s' % text)
    return text.strip()


def _quote(query):
    if '%20' in query:
        query = query.replace('%20', ' ')
    return quote(query)


def _is_not_none(item):
    if item is not None and item.get('size', '0') == '0':
        item = None
    return item is not None


def _get_content_type(video_type):
    content_type = None

    if video_type == 'movie':
        content_type = 'movie'
    elif video_type == 'episode':
        content_type = 'show'

    return content_type


def _get_search_type(video_type):
    search_type = None

    if video_type == 'movie':
        search_type = '1'
    elif video_type == 'episode':
        search_type = '4'

    return search_type


def _get_search_results(server, processed):
    server_uuid = server.get_uuid()

    results = []

    if _is_not_none(processed):
        results = list(map(lambda x: (server_uuid, processed, x), processed))

    return results
