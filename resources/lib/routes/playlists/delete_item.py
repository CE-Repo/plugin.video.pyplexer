# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.common import get_argv
from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n
from plex.network import Plex
from storage.data_cache import DATA_CACHE

LOG = Logger()


def run(context):
    _dialog = xbmcgui.Dialog()
    context.plex_network = Plex(context.settings, load=True)

    server_uuid = get_argv()[2]
    metadata_id = get_argv()[3]

    playlist_title = get_argv()[4]
    playlist_item_id = get_argv()[5]

    path = get_argv()[6]

    LOG.debug('Deleting playlist item at: %s' % playlist_item_id)

    server = context.plex_network.get_server_from_uuid(server_uuid)
    tree = server.get_metadata(metadata_id)

    item = tree[0]
    item_title = item.get('title', '')
    item_image = server.get_kodi_header_formatted_url(
        server.join_url(server.get_url_location(), item.get('thumb'))
    )

    result = _dialog.yesno(i18n('Confirm playlist item delete?'),
                           i18n('Delete from the playlist?') %
                           (item_title, playlist_title))
    if result:
        LOG.debug('Deleting....')
        response = server.delete_playlist_item(playlist_item_id, path)
        if response and not response.get('status'):
            _dialog.notification(CONFIG['name'], i18n('has been removed the playlist') %
                                 (item_title, playlist_title), item_image)
            DATA_CACHE.delete_cache(True)
            xbmc.executebuiltin('Container.Refresh')
            return

    _dialog.notification(CONFIG['name'], i18n('Unable to remove from the playlist') %
                         (item_title, playlist_title), item_image)
