# -*- coding: utf-8 -*-

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.common import get_argv
from core.logger import Logger
from core.strings import i18n
from plex.network import Plex

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)

    server_uuid = get_argv()[2]
    metadata_id = get_argv()[3]

    LOG.debug('Deleting media at: %s' % metadata_id)

    result = xbmcgui.Dialog().yesno(i18n('Confirm file delete?'),
                                    i18n('Delete this item? This action will delete media '
                                         'and associated data files.'))

    if result:
        LOG.debug('Deleting....')
        server = context.plex_network.get_server_from_uuid(server_uuid)
        server.delete_metadata(metadata_id)
        xbmc.executebuiltin('Container.Refresh')
