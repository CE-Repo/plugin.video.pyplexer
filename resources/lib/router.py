# -*- coding: utf-8 -*-

import platform
import sys
import time

from core.common import get_handle
from core.common import get_params
from core.constants import COMMANDS
from core.constants import CONFIG
from core.constants import MODES
from core.context import Context
from core.logger import Logger
from core.settings import AddonSettings

# pylint: disable=import-outside-toplevel

LOG = Logger()


def run(start_time):  # pylint: disable=too-many-locals, too-many-statements, too-many-branches, too-many-return-statements
    context = Context()
    context.settings = AddonSettings()

    if context.settings.wake_on_lan():
        from core.wake_on_lan import wake_servers
        wake_servers(context)

    context.params = get_params()

    try:
        mode = int(context.params.get('mode', MODES.UNSET))
    except ValueError:
        mode = context.params.get('mode')

    command = context.params.get('command', COMMANDS.UNSET)
    path_mode = context.params.get('path_mode')

    library = path_mode is not None and path_mode.startswith('library/')
    media_id = context.params.get('media_id')
    server_uuid = context.params.get('server_uuid')

    url = context.params.get('url')

    context.settings.set_picture_mode(context.params.get('content_type') == 'image')

    _start({
        'mode': mode,
        'command': command,
        'url': url,
        'params': context.params,
        'server_uuid': server_uuid,
        'media_id': media_id
    })

    if command == COMMANDS.REFRESH:
        from routes.browse import refresh
        refresh.run(context)
        return _finished(start_time)

    if command == COMMANDS.SWITCHUSER:
        from routes.account import switch_user
        switch_user.run(context)
        return _finished(start_time)

    if command == COMMANDS.SIGNOUT:
        from routes.account import sign_out
        sign_out.run(context)
        return _finished(start_time)

    if command == COMMANDS.SIGNIN:
        from routes.account import sign_in
        sign_in.run(context)
        return _finished(start_time)

    if command == COMMANDS.MANAGEMYPLEX:
        from routes.account import my_plex
        my_plex.run(context)
        return _finished(start_time)

    if command == COMMANDS.MANAGESERVERS:
        from routes.servers import manage
        manage.run(context)
        return _finished(start_time)

    if command == COMMANDS.SELECTSERVER:
        from routes.servers import select
        select.run(context)
        return _finished(start_time)

    if command == COMMANDS.DETECTSERVERS:
        from routes.servers import detect
        detect.run(context)
        return _finished(start_time)

    if command == COMMANDS.ADD_WATCHLIST:
        from routes.browse import provider
        provider.watchlist_add(context)
        return _finished(start_time)

    if command == COMMANDS.REMOVE_WATCHLIST:
        from routes.browse import provider
        provider.watchlist_remove(context)
        return _finished(start_time)

    if command == COMMANDS.ADD_EXTERNAL_WATCHLIST:
        from routes.browse import provider
        provider.watchlist_add_external(context)
        return _finished(start_time)

    if command == COMMANDS.REMOVE_EXTERNAL_WATCHLIST:
        from routes.browse import provider
        provider.watchlist_remove_external(context)
        return _finished(start_time)

    if command == COMMANDS.TOGGLE_EXTERNAL_WATCHLIST:
        from routes.browse import provider
        provider.watchlist_toggle_external(context)
        return _finished(start_time)

    if command == COMMANDS.DELETEREFRESH:
        from routes.library import delete_and_refresh
        delete_and_refresh.run(context)
        return _finished(start_time)

    if command == COMMANDS.UPDATE:
        from routes.library import refresh_server
        refresh_server.run(context)
        return _finished(start_time)

    # Mark an item as watched/unwatched in plex
    if command == COMMANDS.WATCH:
        from routes.library import watch_status
        watch_status.run(context)
        return _finished(start_time)

    # Hide an item from the Continue Watching hub
    if command == COMMANDS.REMOVE_ON_DECK:
        from routes.library import continue_watching
        continue_watching.remove(context)
        return _finished(start_time)

    # delete media from PMS
    if command == COMMANDS.DELETE:
        from routes.library import delete_media
        delete_media.run(context)
        return _finished(start_time)

    # Allow a master server to be selected (for myPlex Queue)
    if command == COMMANDS.MASTER:
        from routes.servers import set_master
        set_master.run(context)
        return _finished(start_time)

    if command == COMMANDS.DELETEPLAYLIST:
        from routes.playlists import delete
        delete.run(context)
        return _finished(start_time)

    if command == COMMANDS.DELETEFROMPLAYLIST:
        from routes.playlists import delete_item
        delete_item.run(context)
        return _finished(start_time)

    if command == COMMANDS.ADDTOPLAYLIST:
        from routes.playlists import add_item
        add_item.run(context)
        return _finished(start_time)

    if command == COMMANDS.TEST_SKIP_INTRO_DIALOG:
        from routes.diagnostics import skip_intro_preview
        skip_intro_preview.run()
        return _finished(start_time)

    if command == COMMANDS.MANAGE_PLAYLIST:
        from routes.playlists import manage
        manage.run(context)
        return _finished(start_time)

    if command == COMMANDS.SELECT_LIBRARY_SECTIONS:
        from routes.library import configure_sections
        configure_sections.run(context, reset=False)
        return _finished(start_time)

    if command == COMMANDS.RESET_LIBRARY_SECTIONS:
        from routes.library import configure_sections
        configure_sections.run(context, reset=True)
        return _finished(start_time)

    if mode in [MODES.TXT_OPEN, MODES.TXT_PLAY]:
        from routes.library import trakt
        trakt.run(context)
        return _finished(start_time)

    if ((path_mode in [MODES.TXT_MOVIES_LIBRARY, MODES.TXT_TVSHOWS_LIBRARY] and
         (mode is None or mode == MODES.UNSET)) or context.params.get('kodi_action')):
        from routes.library import kodi_export
        kodi_export.run(context)
        return _finished(start_time)

    if mode in [MODES.GETCONTENT, MODES.TXT_TVSHOWS, MODES.TXT_MOVIES,
                MODES.TXT_MOVIES_ON_DECK, MODES.TXT_MOVIES_RECENT_ADDED,
                MODES.TXT_MOVIES_RECENT_RELEASE, MODES.TXT_TVSHOWS_ON_DECK,
                MODES.TXT_TVSHOWS_RECENT_ADDED, MODES.TXT_TVSHOWS_RECENT_AIRED]:
        from routes.browse import content
        content.run(context, url, server_uuid, mode)
        return _finished(start_time)

    if mode == MODES.TVSHOWS:
        from routes.media import shows
        shows.run(context, url)
        return _finished(start_time)

    if mode == MODES.MOVIES:
        from routes.media import movies
        movies.run(context, url)
        return _finished(start_time)

    if mode == MODES.ARTISTS:
        from routes.media import artists
        artists.run(context, url)
        return _finished(start_time)

    if mode == MODES.TVSEASONS:
        from routes.media import seasons
        seasons.run(context, url, rating_key=context.params.get('rating_key'),
                            library=library)
        return _finished(start_time)

    if mode == MODES.PLAYLIBRARY:
        from routes.play import library_media
        library_media.run(context, {
            'url': url,
            'server_uuid': server_uuid,
            'media_id': media_id,
            'transcode': int(context.params.get('transcode', 0)) == 1,
            'transcode_profile': context.params.get('transcode_profile')
        })
        return _finished(start_time)

    if mode == MODES.TVEPISODES:
        from routes.media import episodes
        episodes.run(context, url, rating_key=context.params.get('rating_key'),
                             library=library)
        return _finished(start_time)

    if mode == MODES.PLEXPLUGINS:
        from routes.channels import plugin_listing
        plugin_listing.run(context, url)
        return _finished(start_time)

    if mode == MODES.PROCESSXML:
        from routes.media import xml_listing
        xml_listing.run(context, url)
        return _finished(start_time)

    if mode == MODES.BASICPLAY:
        from routes.play import media_stream
        media_stream.run(context, url)
        return _finished(start_time)

    if mode == MODES.ALBUMS:
        from routes.media import albums
        albums.run(context, url)
        return _finished(start_time)

    if mode == MODES.TRACKS:
        from routes.media import tracks
        tracks.run(context, url)
        return _finished(start_time)

    if mode == MODES.PHOTOS:
        from routes.media import photos
        photos.run(context, url)
        return _finished(start_time)

    if mode == MODES.MUSIC:
        from routes.media import music
        music.run(context, url)
        return _finished(start_time)

    if mode == MODES.VIDEOPLUGINPLAY:
        from routes.play import video_channel
        video_channel.run(context, url, context.params.get('identifier'),
                               context.params.get('indirect'))
        return _finished(start_time)

    if mode == MODES.PLAYLIBRARY_TRANSCODE:
        from routes.play import library_media
        library_media.run(context, {
            'url': url,
            'server_uuid': server_uuid,
            'media_id': media_id,
            'transcode': True,
            'transcode_profile': context.params.get('transcode_profile')
        })
        return _finished(start_time)

    if mode == MODES.LIVETV:
        from routes.browse import live_tv
        live_tv.run(context)
        return _finished(start_time)

    if mode == MODES.LIVETVPLAY:
        from routes.play import live_tv as play_live_tv
        play_live_tv.run(context)
        return _finished(start_time)

    if mode == MODES.MYPLEXQUEUE:
        from routes.browse import myplex_queue
        myplex_queue.run(context)
        return _finished(start_time)

    if mode == MODES.WATCHLIST:
        from routes.browse import provider
        provider.watchlist(context)
        return _finished(start_time)

    if mode == MODES.DISCOVER:
        from routes.browse import provider
        provider.discover(context)
        return _finished(start_time)

    if mode == MODES.PROVIDERBROWSE:
        from routes.browse import provider
        provider.browse(context, url)
        return _finished(start_time)

    if mode == MODES.PROVIDERPLAY:
        from routes.browse import provider
        provider.play(context, context.params.get('guid'), url)
        return _finished(start_time)

    if mode == MODES.CHANNELSEARCH:
        from routes.channels import search
        search.run(context, url, context.params.get('prompt'))
        return _finished(start_time)

    if mode == MODES.CHANNELPREFS:
        from routes.channels import settings
        settings.run(context, url, context.params.get('id'))
        return _finished(start_time)

    if mode == MODES.SHARED_MOVIES:
        from routes.browse import sections
        sections.run(context, content_filter='movies', display_shared=True)
        return _finished(start_time)

    if mode == MODES.SHARED_SHOWS:
        from routes.browse import sections
        sections.run(context, content_filter='tvshows', display_shared=True)
        return _finished(start_time)

    if mode == MODES.SHARED_PHOTOS:
        from routes.browse import sections
        sections.run(context, content_filter='photos', display_shared=True)
        return _finished(start_time)

    if mode == MODES.SHARED_MUSIC:
        from routes.browse import sections
        sections.run(context, content_filter='music', display_shared=True)
        return _finished(start_time)

    if mode == MODES.SHARED_ALL:
        from routes.browse import sections
        sections.run(context, display_shared=True)
        return _finished(start_time)

    if mode == MODES.PLAYLISTS:
        from routes.media import xml_listing
        xml_listing.run(context, url)
        return _finished(start_time)

    if mode == MODES.DISPLAYSERVERS:
        from routes.browse import servers
        servers.run(context, url)
        return _finished(start_time)

    if mode == MODES.WIDGETS:
        from routes.browse import widgets
        widgets.run(context, url)
        return _finished(start_time)

    if mode == MODES.SEARCHALL:
        from routes.search import local
        local.run(context)
        return _finished(start_time)

    if mode == MODES.COMBINED_SECTIONS:
        from routes.browse import combined_sections
        combined_sections.run(context)
        return _finished(start_time)

    if mode == MODES.CONTINUE_WATCHING:
        from routes.browse import on_deck
        context.params['content_type'] = None
        on_deck.run(context)
        return _finished(start_time)

    if mode == MODES.TVSHOWS_ON_DECK:
        from routes.browse import on_deck
        context.params['content_type'] = 'tvshows'
        on_deck.run(context)
        return _finished(start_time)

    if mode == MODES.MOVIES_ON_DECK:
        from routes.browse import on_deck
        context.params['content_type'] = 'movies'
        on_deck.run(context)
        return _finished(start_time)

    if mode == MODES.EPISODES_RECENTLY_ADDED:
        from routes.browse import recently_added
        context.params['content_type'] = 'tvshows'
        recently_added.run(context)
        return _finished(start_time)

    if mode == MODES.MOVIES_RECENTLY_ADDED:
        from routes.browse import recently_added
        context.params['content_type'] = 'movies'
        recently_added.run(context)
        return _finished(start_time)

    if MODES.MOVIES_ALL <= mode <= MODES.PHOTOS_ALL:
        from routes.browse import all_servers
        all_servers.run(context)
        return _finished(start_time)

    if MODES.MOVIES_SEARCH_ALL <= mode <= MODES.TRACKS_SEARCH_ALL:
        from routes.search import all_servers
        all_servers.run(context)
        return _finished(start_time)

    #
    # default actions below
    #

    if get_handle() == -1:
        CONFIG['addon'].openSettings()
        return _finished(start_time)

    from routes.browse import sections
    sections.run(context)
    return _finished(start_time)


def _start(data):
    LOG.notice('%s %s: Kodi %s on %s with Python %s' %
               (CONFIG['name'], CONFIG['version'], CONFIG['kodi_version'],
                platform.uname()[0], '.'.join(map(str, sys.version_info))),
               no_privacy=True)  # force no privacy to avoid redacting version strings

    LOG.notice('Mode |%s| Command |%s| Url |%s| Parameters |%s| Server UUID |%s| Media Id |%s|'
               % (data.get('mode'), data.get('command'), data.get('url'),
                  data.get('params'), data.get('server_uuid'), data.get('media_id')))


def _finished(start_time):
    LOG.notice('Finished. |%.3fs|' % (time.time() - start_time))
