# -*- coding: utf-8 -*-

from urllib.parse import quote
from urllib.parse import urlparse

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_argv
from core.common import get_handle
from core.constants import CONFIG
from core.constants import MODES
from core.context import GUIItem
from core.logger import Logger
from core.strings import i18n
from core.strings import i18n_or
from gui.list_item import create_gui_item
from plex.network import PROVIDER_DISCOVER
from plex.network import Plex
from processing.provider import process_provider

LOG = Logger()


def _ensure_signed_in(context):
    context.plex_network = Plex(context.settings, load=True)
    if context.plex_network.is_myplex_signedin():
        return True

    xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                  message=i18n('myPlex not configured'),
                                  icon=CONFIG['icon'])
    return False


def watchlist(context):
    if not _ensure_signed_in(context):
        return

    tree = context.plex_network.get_watchlist()
    process_provider(context, PROVIDER_DISCOVER, tree, in_watchlist=True)


def watchlist_add(context):
    _watchlist_action(context, add=True)


def watchlist_remove(context):
    _watchlist_action(context, add=False)


def watchlist_add_external(context):
    _watchlist_external_action(context, add=True)


def watchlist_remove_external(context):
    _watchlist_external_action(context, add=False)


def _watchlist_external_action(context, add):
    """Add or remove the focused TMDb Helper item as explicitly requested."""
    context.plex_network = Plex(context.settings, load=False)
    if not context.plex_network.is_myplex_signedin():
        xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                      message=i18n('myPlex not configured'),
                                      icon=CONFIG['icon'])
        return

    argv = get_argv()
    media_type = argv[2].strip() if len(argv) > 2 else None
    external_guid = argv[3].strip() if len(argv) > 3 else None

    rating_key = context.plex_network.resolve_provider_rating_key(external_guid, media_type)
    if not rating_key:
        message = i18n_or('Plex could not match this title',
                          'Plex konnte diesen Titel nicht zuordnen')
        xbmcgui.Dialog().notification(heading=CONFIG['name'], message=message,
                                      icon=CONFIG['icon'])
        return

    if add and context.plex_network.is_provider_watchlisted(rating_key):
        _watchlist_already_added()
        return

    success = context.plex_network.provider_watchlist_action(add, rating_key)
    _watchlist_result(success, add)
    if success:
        xbmc.executebuiltin('Container.Refresh')


def _watchlist_action(context, add):
    context.plex_network = Plex(context.settings, load=False)

    argv = get_argv()
    rating_key = argv[2] if len(argv) > 2 else None
    success = context.plex_network.provider_watchlist_action(add, rating_key)

    _watchlist_result(success, add)
    xbmc.executebuiltin('Container.Refresh')


def _watchlist_result(success, add):
    """Show the localized result shared by direct and external actions."""

    if success and add:
        message = i18n_or('Added to Watchlist',
                          'Zur Merkliste erfolgreich hinzugefügt')
    elif success:
        message = i18n_or('Removed from Watchlist',
                          'Aus Plex Merkliste erfolgreich entfernt')
    else:
        message = i18n_or('Could not update Watchlist',
                          'Merkliste konnte nicht aktualisiert werden')

    xbmcgui.Dialog().notification(heading=CONFIG['name'], message=message, icon=CONFIG['icon'])


def _watchlist_already_added():
    message = i18n_or('Already in Plex Watchlist',
                      'Ist bereits in der Plex Merkliste')
    xbmcgui.Dialog().notification(heading=CONFIG['name'], message=message,
                                  icon=CONFIG['icon'])


def discover(context):
    """Plex Discover feed. Try the account-level Discover provider first; if it
    is not reachable for this account, fall back to the user's own server
    recommendation hubs so the section is never empty."""
    if not _ensure_signed_in(context):
        return

    tree = context.plex_network.get_discover_hubs()
    if tree is not None and len(list(tree)):
        LOG.debug('Using account Discover feed')
        process_provider(context, PROVIDER_DISCOVER, tree)
        return

    LOG.debug('Account Discover feed unavailable, using server hubs')
    _server_hubs(context)


def _server_hubs(context):
    xbmcplugin.setContent(get_handle(), 'videos')

    servers = context.plex_network.get_server_list()
    prefix_needed = len([s for s in servers if not s.is_offline()]) > 1

    items = []
    for server in servers:
        if server.is_offline() or server.is_secondary():
            continue

        try:
            tree = server.processed_xml('/hubs')
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('hub lookup failed on %s: %s' % (server.get_name(), error))
            continue

        if tree is None:
            continue

        prefix = (server.get_name() + ': ') if prefix_needed else ''

        for hub in tree.iter('Hub'):
            if hub.get('size') == '0':
                continue

            title = hub.get('title')
            key = hub.get('key') or hub.get('hubKey')
            if not title or not key:
                continue

            details = {'title': prefix + title}
            extra_data = {'type': 'Folder', 'mode': MODES.PROCESSXML}
            item_url = server.join_url(server.get_url_location(), key)
            items.append(create_gui_item(context, GUIItem(item_url, details, extra_data)))

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())


def browse(context, url):
    if not _ensure_signed_in(context):
        return

    tree = context.plex_network.get_provider_tree(url)
    parts = urlparse(url)
    base = '%s://%s' % (parts.scheme, parts.netloc)
    process_provider(context, base, tree)


def play(context, guid=None, detail_url=None):
    """Play a Discover/Watchlist item.

    Movies/episodes are matched to the user's own servers via their plex:// guid.
    Plex-hosted clips (trailers/extras) - and anything not found on a server - are
    streamed directly from the Plex provider instead.
    """
    context.plex_network = Plex(context.settings, load=True)

    if guid:
        resolved = _resolve_on_servers(context, guid)
        if resolved:
            server_uuid, rating_key = resolved
            LOG.debug('Resolved guid %s -> server %s, ratingKey %s' %
                      (guid, server_uuid, rating_key))
            from routes.play import library_media
            library_media.run(context, {
                'server_uuid': server_uuid,
                'media_id': rating_key,
                'transcode': False,
                'transcode_profile': None,
            })
            return

    stream = _provider_stream(context, detail_url)
    if stream:
        LOG.debug('Playing provider stream: %s' % stream)
        xbmcplugin.setResolvedUrl(get_handle(), True, xbmcgui.ListItem(path=stream))
        return

    LOG.debug('Unable to resolve guid %s / url %s' % (guid, detail_url))
    xbmcplugin.setResolvedUrl(get_handle(), False, xbmcgui.ListItem())
    xbmcgui.Dialog().notification(
        heading=CONFIG['name'],
        message=i18n('This title is not available on any of your servers'),
        icon=CONFIG['icon'])


def _provider_stream(context, detail_url):
    """Fetch a provider item's metadata and return a directly playable Part URL."""
    if not detail_url:
        return None

    tree = context.plex_network.get_provider_tree(detail_url)
    if tree is None:
        return None

    parts = urlparse(detail_url)
    base = '%s://%s' % (parts.scheme, parts.netloc)
    token = context.plex_network.get_provider_token()

    for part in tree.iter('Part'):
        key = part.get('key')
        if not key:
            continue
        url = key if key.startswith('http') else base + key
        if token:
            sep = '&' if '?' in url else '?'
            url = '%s%sX-Plex-Token=%s' % (url, sep, token)
        return url

    return None


def _resolve_on_servers(context, guid):
    if not guid:
        return None

    encoded = quote(guid, safe='')
    for server in context.plex_network.get_server_list():
        if server.is_offline() or server.is_secondary():
            continue

        try:
            tree = server.processed_xml('/library/all?guid=%s' % encoded)
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('guid lookup failed on %s: %s' % (server.get_name(), error))
            continue

        if tree is None:
            continue

        for video in tree.iter('Video'):
            rating_key = video.get('ratingKey')
            if rating_key:
                return server.get_uuid(), rating_key

    return None
