# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error

from core.logger import Logger
from core.strings import i18n
from core.utils import get_master_server
from plex.network import Plex

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)
    servers = get_master_server(context, all_servers=True)
    LOG.debug(str(servers))

    current_master = context.settings.master_server()

    display_option_list = []
    append_server = display_option_list.append

    for address in servers:
        found_server = address.get_name()
        if found_server == current_master:
            found_server = found_server + '*'
        append_server(found_server)

    result = xbmcgui.Dialog().select(i18n('Select master server'), display_option_list)
    if result == -1:
        return

    LOG.debug('Setting master server to: %s' % servers[result].get_name())
    context.settings.set_master_server(servers[result].get_name())
