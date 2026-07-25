# -*- coding: utf-8 -*-

import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.context import Item
from core.logger import Logger
from gui.builders.episode import create_episode_item
from gui.builders.movie import create_movie_item
from plex.network import Plex

LOG = Logger()


def run(context):
    context.plex_network = Plex(context.settings, load=True)
    content_type = context.params.get('content_type')
    server_list = context.plex_network.get_server_list()

    items = []
    LOG.debug('Using list of %s servers: %s' % (len(server_list), server_list))
    for server in server_list:
        sections = server.get_sections()
        for section in sections:
            if section.content_type() == content_type:
                items += _list_content(context, server, int(section.get_key()))

    if items:
        xbmcplugin.setContent(get_handle(), content_type)
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=False)


def _list_content(context, server, section):
    tree = server.get_ondeck(section=section)
    if tree is None:
        return []

    branches = tree.iter('Video')

    if not branches:
        return []

    items = []
    append_item = items.append

    for content in branches:
        item = Item(server, server.get_url_location(), tree, content)
        if content.get('type') == 'episode':
            append_item(create_episode_item(context, item))
        elif content.get('type') == 'movie':
            append_item(create_movie_item(context, item))

    return items
