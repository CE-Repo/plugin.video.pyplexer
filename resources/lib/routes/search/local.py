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

    # one line that says what the caller asked for and what came back, so a
    # player handing over too little is visible in the log
    LOG.debug('Search: query=%s title=%s originaltitle=%s year=%s showtitle=%s '
              'season=%s episode=%s -> %s lookup' %
              (params.get('query'), params.get('title'), params.get('originaltitle'),
               _wanted_year(params), params.get('showtitle'), params.get('season'),
               params.get('episode'), 'exact' if _is_precise(params) else 'plain'))

    succeeded = False
    search_results = search(context)
    LOG.debug('Search returned %s item(s)' % len(search_results))
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
    elif context.params.get('video_type') == 'episode':
        results = _refine_episodes(context, results)

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

    year = _wanted_year(context.params)

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

    # every copy of the right film is kept - a Full HD and a 4K item are two
    # things to choose from, not a duplicate
    return matches


def _refine_episodes(context, results):
    """Keep the episode the caller asked for and nothing else.  The fallback
    searches for the episode title, and Plex answers 'Das Puzzle' with every
    episode of that name from every show, so season and episode have to fit.

    The show is only allowed to differ when no item carries the requested one,
    because a library may hold the show under a localised name.
    """
    season = _as_int(context.params.get('season'))
    episode = _as_int(context.params.get('episode'))
    if season is None or episode is None:
        return results  # the keyboard search has to stay broad

    show = normalise_title(context.params.get('showtitle'))

    exact = []
    close = []

    for entry in results:
        element = entry[2]

        if (_as_int(element.get('parentIndex')) != season or
                _as_int(element.get('index')) != episode):
            continue

        if show and normalise_title(element.get('grandparentTitle')) == show:
            exact.append(entry)
        else:
            close.append(entry)

    matches = exact or close
    if not matches:
        LOG.debug('No item matches %s S%sE%s, the caller gets nothing rather '
                  'than the wrong episode' % (show or '?', season, episode))

    # every copy of the right episode is kept - a Full HD and a 4K item are two
    # things to choose from, not a duplicate
    return matches


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

    return results


def _wanted_titles(params):
    """The caller may know the title in another language than the library."""
    titles = {normalise_title(params.get('title')),
              normalise_title(params.get('originaltitle'))}
    titles.discard('')
    return titles


def _wanted_year(params):
    """The year the caller asked for.  Players do not all fill ``year``; some
    only hand over the release date, and one that names neither gets no year at
    all rather than a guess."""
    year = _as_int(params.get('year'))
    if year:
        return year

    premiered = params.get('premiered') or params.get('release_date') or ''
    return _as_int(str(premiered)[:4])


def _sort_results(context, results):
    """Newest first, with the closest match on top: what the caller asked for
    should not sit below a namesake from twenty years ago.  Copies of one film
    are kept together with the best quality first."""
    # sorting twice, the second pass is stable and keeps the quality order
    # inside a group of copies
    results = sorted(results, key=_best_media_score, reverse=True)

    wanted = _wanted_titles(context.params)

    if context.params.get('video_type') == 'episode':
        show = normalise_title(context.params.get('showtitle'))
        numbers = (_as_int(context.params.get('season')),
                   _as_int(context.params.get('episode')))
        return sorted(results,
                      key=lambda entry: _episode_order(entry[2], wanted, show, numbers))

    year = _wanted_year(context.params)

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


def _episode_order(element, wanted, show, numbers):
    """Requested show first, then by year, then season and episode."""
    season, episode = numbers
    found_show = normalise_title(element.get('grandparentTitle'))
    found_year = _as_int(element.get('year')) or 0
    found_season = _as_int(element.get('parentIndex')) or 0
    found_episode = _as_int(element.get('index')) or 0

    if show:
        show_rank = 0 if found_show == show else 1
    elif wanted:
        show_rank = 0 if _title_matches(element, wanted) else 1
    else:
        show_rank = 0

    if season is None or episode is None:
        wanted_rank = 0
    else:
        wanted_rank = 0 if (found_season == season and found_episode == episode) else 1

    return (
        -found_year,
        show_rank,
        wanted_rank,
        found_show,
        found_season,
        found_episode,
    )


def _best_media_score(entry):
    """Quality of the best version an item holds, used to put the 4K copy of a
    film above its Full HD copy."""
    element = entry[2]
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
    return bool(_wanted_year(params) or _episode_wanted(params))


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
