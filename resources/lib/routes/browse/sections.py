# -*- coding: utf-8 -*-

import xbmcgui  # pylint: disable=import-error
import xbmcplugin  # pylint: disable=import-error

from core.common import get_handle
from core.constants import COMMANDS
from core.constants import CONFIG
from core.constants import MODES
from core.context import GUIItem
from core.logger import Logger
from core.strings import i18n
from gui.list_item import create_gui_item
from plex.network import Plex
from processing.pagination import paginate_local_items

LOG = Logger()
WINDOW = xbmcgui.Window(10000)

#: Holds the server a rediscovery was already spent on, so an unreachable one
#: is retried once per session instead of before every listing.
RETRY_PROPERTY = 'plugin.video.pyplexer-offline-retry'


def run(context, content_filter=None, display_shared=False):
    context.plex_network = Plex(context.settings, load=True)
    xbmcplugin.setContent(get_handle(), 'files')

    server_list = context.plex_network.get_active_server_list()
    LOG.debug('Using list of %s servers: %s' % (len(server_list), server_list))

    items = []
    append_item = items.append

    menus = context.settings.show_menus()

    server_section_menus, playlist_section_menus = \
        server_section_menus_items(context, server_list, content_filter, display_shared, menus)

    if server_section_menus:
        items += combined_sections_item(context)
    else:
        _report_empty_server(context, server_list)

    items += server_section_menus

    if display_shared:
        items = paginate_local_items(context, items)
        if items:
            xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

        xbmcplugin.endOfDirectory(get_handle(),
                                  cacheToDisc=context.settings.cache_directory())
        return

    if menus.get('playlists') and context.plex_network.is_myplex_signedin():
        items += playlist_section_menus

    if menus.get('pyplexer_playlist') and context.plex_network.is_myplex_signedin():
        items += pyplexer_playlist_item(context)

    # For each of the servers we have identified
    if menus.get('queue') and context.plex_network.is_myplex_signedin():
        details = {
            'title': i18n('myPlex Queue')
        }
        extra_data = {
            'type': 'Folder',
            'mode': MODES.MYPLEXQUEUE
        }
        gui_item = GUIItem('http://myplexqueue', details, extra_data)
        append_item(create_gui_item(context, gui_item))

    if menus.get('watchlist') and context.plex_network.is_myplex_signedin():
        details = {
            'title': i18n('Watchlist')
        }
        extra_data = {
            'type': 'Folder',
            'mode': MODES.WATCHLIST
        }
        gui_item = GUIItem('http://watchlist', details, extra_data)
        append_item(create_gui_item(context, gui_item))

    if menus.get('discover') and context.plex_network.is_myplex_signedin():
        details = {
            'title': i18n('Discover')
        }
        extra_data = {
            'type': 'Folder',
            'mode': MODES.DISCOVER
        }
        gui_item = GUIItem('http://discover', details, extra_data)
        append_item(create_gui_item(context, gui_item))

    # a DVR belongs to a server, the free channels to the account; one entry
    # gathers both, so it is not tied to being signed in
    if menus.get('live_tv'):
        details = {
            'title': i18n('Live TV')
        }
        extra_data = {
            'type': 'Folder',
            'mode': MODES.LIVETV
        }
        gui_item = GUIItem('http://livetv', details, extra_data)
        append_item(create_gui_item(context, gui_item))

    items += server_additional_menu_items(context, server_list, content_filter, menus)
    items += action_menu_items(context)
    items = paginate_local_items(context, items)

    if items:
        xbmcplugin.addDirectoryItems(get_handle(), items, len(items))

    xbmcplugin.endOfDirectory(get_handle(), cacheToDisc=context.settings.cache_directory())


def pyplexer_playlist_item(context):
    details = {
        'title': i18n('PyPlexer Playlist')
    }
    extra_data = {
        'type': 'file'
    }

    item_url = 'cmd:' + COMMANDS.MANAGE_PLAYLIST
    gui_item = GUIItem(item_url, details, extra_data)
    return [create_gui_item(context, gui_item)]


def _report_empty_server(context, server_list):
    """Say why a chosen server shows nothing, rather than showing nothing.

    An empty menu after a switch is indistinguishable from a broken add-on, so
    the reason goes to the log per server and the notification tells the user
    the switch itself worked.
    """
    chosen = context.plex_network.active_server_name()
    if not chosen:
        return

    offline = False
    for server in server_list:
        offline = offline or server.is_offline()
        LOG.debug('%s: offline=%s, secondary=%s, %s section(s): %s' %
                  (server.get_name(), server.is_offline(), server.is_secondary(),
                   len(server.get_sections()),
                   [section.get_title() for section in server.get_sections()]))

    reason = i18n('No libraries found')
    if offline:
        reason = i18n('Offline')
        chosen_uuid = context.settings.active_server()

        # The server list is cached without an expiry, and a server marked
        # offline is never asked again - its requests answer from the flag
        # alone.  Picking it is reason enough for one rediscovery, but only
        # one: a server that stays away would otherwise have every second
        # listing pay for a full discovery.
        if WINDOW.getProperty(RETRY_PROPERTY) != chosen_uuid:
            WINDOW.setProperty(RETRY_PROPERTY, chosen_uuid)
            WINDOW.setProperty('plugin.video.pyplexer-refresh.servers', 'true')
            LOG.debug('Chosen server is flagged offline, armed a rediscovery')
        else:
            LOG.debug('Chosen server is still offline after a rediscovery')

    xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                  message='%s: %s' % (chosen, reason),
                                  icon=CONFIG['icon'])


def select_server_item(context):
    """The switch between one server and all of them; pointless with one."""
    if len(context.plex_network.get_server_list()) < 2:
        return []

    title = i18n('Select server')
    chosen = context.plex_network.active_server_name()
    if chosen:
        # so the menu says which server the listing above belongs to
        title = '%s (%s)' % (title, chosen)

    details = {
        'title': title
    }
    extra_data = {
        'type': 'file'
    }

    item_url = 'cmd:' + COMMANDS.SELECTSERVER
    gui_item = GUIItem(item_url, details, extra_data)
    return [create_gui_item(context, gui_item)]


def combined_sections_item(context):
    details = {
        'title': i18n('Combined Sections')
    }
    extra_data = {
        'type': 'Folder',
        'mode': MODES.COMBINED_SECTIONS
    }
    gui_item = GUIItem('http://combined_sections', details, extra_data)
    return [create_gui_item(context, gui_item)]


def server_section_menus_items(context, server_list, content_filter, display_shared, menus):
    settings = {
        'picture_mode': context.settings.get_picture_mode(),
        'prefix_server': context.settings.prefix_server(),
        'use_context_menus': not context.settings.skip_context_menus(),
    }

    items = []
    playlist_items = []
    for server in server_list:

        sections = server.get_sections()
        url_location = server.get_url_location()
        server_uuid = server.get_uuid()
        server_name = server.get_name()

        prefix_server = context.settings.prefix_server()
        if not prefix_server or (prefix_server and len(server_list) > 1):
            prefix = server.get_name() + ': '
        else:
            prefix = ''

        server_items = []
        for section in sections:

            if (display_shared and server.is_owned() or
                    (content_filter is not None and section.content_type() != content_filter)):
                continue

            if section.content_type() is None:
                LOG.debug('Ignoring section %s: %s of type %s as unable to process'
                          % (server_name, section.get_title(), section.get_type()))
                continue

            if not settings.get('picture_mode') and section.is_photo():
                # photos only work from the picture add-ons
                continue

            details = {
                'title': prefix + section.get_title()
            }

            extra_data = {
                'type': 'Folder'
            }

            path = section.get_path()

            if context.settings.secondary_menus():
                mode = MODES.GETCONTENT
            else:
                mode = section.mode()
                path = path + '/all'

            extra_data['mode'] = mode
            section_url = server.join_url(url_location, path)
            context_menu = None
            if settings.get('use_context_menus'):
                context_menu = [(i18n('Refresh library section'),
                                 'RunScript(' + CONFIG['id'] + ', update, %s, %s)' %
                                 (server_uuid, section.get_key()))]

            # Build that listing..
            gui_item = GUIItem(section_url, details, extra_data, context_menu)
            server_items.append(create_gui_item(context, gui_item))

        if server_items:
            if menus.get('playlists'):
                # create playlist link
                details = {
                    'title': prefix + i18n('Playlists')
                }
                extra_data = {
                    'type': 'Folder',
                    'mode': MODES.PLAYLISTS
                }
                item_url = server.join_url(url_location, 'playlists')
                gui_item = GUIItem(item_url, details, extra_data)
                playlist_items.append(create_gui_item(context, gui_item))

            items += server_items

    return items, playlist_items


def server_additional_menu_items(context, server_list, content_filter, menus):
    prefix_server = context.settings.prefix_server()

    items = []
    append_item = items.append
    for server in server_list:

        if server.is_offline() or server.is_secondary():
            continue

        # Plex plugin handling
        if (content_filter is not None) and (content_filter != 'plugins'):
            continue

        if not prefix_server or (prefix_server and len(server_list) > 1):
            prefix = server.get_name() + ': '
        else:
            prefix = ''

        if menus.get('widgets'):
            # create Widgets link
            details = {
                'title': prefix + i18n('Widgets')
            }
            extra_data = {
                'type': 'Folder',
                'mode': MODES.WIDGETS
            }

            item_url = server.get_url_location()
            gui_item = GUIItem(item_url, details, extra_data)
            append_item(create_gui_item(context, gui_item))

    return items


def action_menu_items(context):
    items = []
    append_item = items.append
    if context.plex_network.is_myplex_signedin():

        if context.plex_network.is_plexhome_enabled():
            details = {
                'title': i18n('Switch User')
            }
            extra_data = {
                'type': 'file'
            }

            item_url = 'cmd:' + COMMANDS.SWITCHUSER
            gui_item = GUIItem(item_url, details, extra_data)
            append_item(create_gui_item(context, gui_item))

        details = {
            'title': i18n('Sign Out')
        }
        extra_data = {
            'type': 'file'
        }

        item_url = 'cmd:' + COMMANDS.SIGNOUT
        gui_item = GUIItem(item_url, details, extra_data)
        append_item(create_gui_item(context, gui_item))

        details = {
            'title': i18n('Detect Servers')
        }
        extra_data = {
            'type': 'file'
        }
        item_url = 'cmd:' + COMMANDS.DETECTSERVERS
        gui_item = GUIItem(item_url, details, extra_data)
        append_item(create_gui_item(context, gui_item))

        items += select_server_item(context)

        details = {
            'title': i18n('Manage Servers')
        }
        extra_data = {
            'type': 'file'
        }
        item_url = 'cmd:' + COMMANDS.MANAGESERVERS
        gui_item = GUIItem(item_url, details, extra_data)
        append_item(create_gui_item(context, gui_item))

        if context.settings.cache():
            details = {
                'title': i18n('Clear Caches')
            }
            extra_data = {
                'type': 'file'
            }
            item_url = 'cmd:' + COMMANDS.DELETEREFRESH
            gui_item = GUIItem(item_url, details, extra_data)
            append_item(create_gui_item(context, gui_item))
    else:
        details = {
            'title': i18n('Sign In')
        }
        extra_data = {
            'type': 'file'
        }

        item_url = 'cmd:' + COMMANDS.SIGNIN
        gui_item = GUIItem(item_url, details, extra_data)
        append_item(create_gui_item(context, gui_item))

    return items
