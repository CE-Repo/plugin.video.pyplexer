# -*- coding: utf-8 -*-

from urllib.parse import urlencode

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.logger import Logger
from core.strings import i18n
from core.utils import get_xml
from plex.network import Plex

LOG = Logger()


def run(context, url, setting_id):
    """
        Take the setting XML and parse it to create an updated
        string with the new settings.  For the selected value, create
        a user input screen (text or list) to update the setting.
        @ input: url
        @ return: nothing
    """

    context.plex_network = Plex(context.settings, load=True)

    LOG.debug('Setting preference for ID: %s' % setting_id)

    if not setting_id:
        LOG.debug('ID not set')
        return

    tree = get_xml(context, url)
    if tree is None:
        return

    set_url = '%s/set?' % url
    set_params = {}

    plugins = tree.iter()

    for plugin in plugins:

        if plugin.get('id') == setting_id:
            LOG.debug('Found correct id entry for: %s' % setting_id)
            sid = setting_id

            label = plugin.get('label', i18n('Enter value'))
            option = plugin.get('option')
            value = plugin.get('value')

            if plugin.get('type') == 'text':
                LOG.debug('Setting up a text entry screen')
                keyboard = xbmc.Keyboard(value, i18n('Enter value'))
                keyboard.setHeading(label)
                keyboard.setHiddenInput(option == 'hidden')

                keyboard.doModal()
                if keyboard.isConfirmed():
                    value = keyboard.getText()
                    LOG.debug('Value input: %s ' % value)
                else:
                    LOG.debug('User cancelled dialog')
                    return

            elif plugin.get('type') == 'enum':
                LOG.debug('Setting up an enum entry screen')

                values = plugin.get('values').split('|')

                setting_screen = xbmcgui.Dialog()
                value = setting_screen.select(label, values)
                if value == -1:
                    LOG.debug('User cancelled dialog')
                    return
            else:
                LOG.debug('Unknown option type: %s' % plugin.get('id'))

        else:
            value = plugin.get('value')
            sid = plugin.get('id')

        set_params[sid] = value

    set_url += urlencode(set_params)

    LOG.debug('Settings URL: %s' % set_url)
    context.plex_network.talk_to_server(set_url)
    xbmc.executebuiltin('Container.Refresh')
