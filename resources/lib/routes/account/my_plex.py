# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error

from core.logger import Logger
from core.strings import i18n
from plex.network import Plex
from plex.signin import manage_plex
from plex.signin import sign_in_to_plex

LOG = Logger()


def run(context):
    _dialog = xbmcgui.Dialog()
    context.plex_network = Plex(context.settings, load=False)

    has_access = True
    if not context.plex_network.is_myplex_signedin():
        has_access = False
        result = _dialog.yesno(i18n('Manage myPlex'),
                               i18n('You are not currently logged into myPlex. '
                                    'Continue to sign in, or cancel to return'))
        if result:
            has_access = sign_in_to_plex(context, refresh=False)
            context.plex_network = Plex(context.settings, load=False)

    elif not context.plex_network.is_admin():
        has_access = False
        _ = _dialog.ok(i18n('Manage myPlex'),
                       i18n('To access these screens you must be logged in as '
                            'an admin user. Switch user and try again'))

    if has_access:
        manage_plex(context)
