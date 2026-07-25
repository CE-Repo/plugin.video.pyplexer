# -*- coding: utf-8 -*-

from urllib.parse import unquote_plus

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.logger import Logger
from core.strings import i18n
from core.utils import get_xml
from plex.network import Plex

LOG = Logger()


def run(context, url, name):
    _dialog = xbmcgui.Dialog()
    context.plex_network = Plex(context.settings, load=True)

    tree = get_xml(context, url)
    if tree is None:
        return

    try:
        name = unquote_plus(name)
    except Exception:  # pylint: disable=broad-except
        pass

    operations = {}
    plugins = tree.findall('Directory')
    for idx, plugin in enumerate(plugins):
        operations[idx] = plugin.get('title')

        # If we find an install option, switch to a yes/no dialog box
        if operations[idx].lower() == 'install':
            LOG.debug('Not installed.  Print dialog')
            result = \
                _dialog.yesno(i18n('Plex Online'), i18n('About to install') + ' ' + name)

            if result:
                LOG.debug('Installing....')
                _ = get_xml(context, url + '/install')

            return

    # Else continue to a selection dialog box
    result = _dialog.select(i18n('This plugin is already installed'),
                            list(operations.values()))

    if result == -1:
        LOG.debug('No option selected, cancelling')
        return

    LOG.debug('Option %s selected.  Operation is %s' % (result, operations[result]))

    item_url = url + '/' + operations[result].lower()
    _ = get_xml(context, item_url)

    xbmc.executebuiltin('Container.Refresh')
