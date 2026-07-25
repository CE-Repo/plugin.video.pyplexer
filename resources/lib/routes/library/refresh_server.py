# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error

from core.common import get_argv
from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n
from plex.network import Plex

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    server_uuid = get_argv()[2]
    section_id = get_argv()[3]

    server = context.plex_network.get_server_from_uuid(server_uuid)
    server.refresh_section(section_id)

    LOG.debug('Library refresh requested')
    xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                  message=i18n('Library refresh started'),
                                  icon=CONFIG['icon'])
