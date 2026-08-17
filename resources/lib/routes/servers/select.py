# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.logger import Logger
from core.strings import i18n
from plex.network import Plex
from storage.data_cache import DATA_CACHE

LOG = Logger()
WINDOW = xbmcgui.Window(10000)

#: Set by the listing when it spent a rediscovery on an offline server
RETRY_PROPERTY = 'plugin.video.pyplexer-offline-retry'


def run(context):
    """Let the user browse one server instead of all of them."""
    context.plex_network = Plex(context.settings, load=True)

    servers = [server for server in context.plex_network.get_server_list()
               if not server.is_secondary()]
    if not servers:
        xbmcgui.Dialog().notification(heading=i18n('Select server'),
                                      message=i18n('No servers found'))
        return

    chosen = context.settings.active_server()

    # the first entry undoes the choice again
    labels = [_label(i18n('All servers'), not chosen)]
    uuids = ['']

    for server in servers:
        name = server.get_name()
        if server.is_offline():
            # so an unreachable server is visible before it is picked, not
            # afterwards through an empty listing
            name = '%s [%s]' % (name, i18n('Offline'))

        labels.append(_label(name, server.get_uuid() == chosen))
        uuids.append(server.get_uuid())

    result = xbmcgui.Dialog().select(i18n('Select server'), labels)
    if result == -1:
        return

    if uuids[result] == chosen:
        LOG.debug('Server choice unchanged')
        return

    LOG.debug('Browsing %s from now on' % (uuids[result] or 'every server'))
    context.settings.set_active_server(uuids[result])

    # choosing again is a deliberate second attempt; let it cost a rediscovery
    WINDOW.clearProperty(RETRY_PROPERTY)

    # the listings that are about to be rebuilt were cached per server
    DATA_CACHE.delete_cache(True)
    xbmc.executebuiltin('Container.Refresh')


def _label(name, chosen):
    if chosen:
        return '[COLOR=lightgreen]%s[/COLOR]' % name
    return name
