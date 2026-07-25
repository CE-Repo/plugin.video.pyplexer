# -*- coding: utf-8 -*-

from urllib.parse import quote
from urllib.parse import unquote

import xbmc  # pylint: disable=import-error

from core.logger import Logger
from core.strings import i18n
from plex.network import Plex
from processing.plex_plugins import process_plex_plugins

LOG = Logger()


def run(context, url, prompt):
    """
        When we encounter a search request, branch off to this function to generate the keyboard
        and accept the terms.  This URL is then fed back into the correct function for
        onward processing.
    """
    context.plex_network = Plex(context.settings, load=True)

    if prompt:
        prompt = unquote(prompt)
    else:
        prompt = i18n('Enter search term')

    keyboard = xbmc.Keyboard('', i18n('Search...'))
    keyboard.setHeading(prompt)
    keyboard.doModal()
    if keyboard.isConfirmed():
        text = keyboard.getText()
        LOG.debug('Search term input: %s' % text)
        url = url + '&query=' + quote(text)
        process_plex_plugins(context, url)
