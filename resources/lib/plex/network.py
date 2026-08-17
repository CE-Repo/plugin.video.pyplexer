# -*- coding: utf-8 -*-

import base64
import hashlib
import socket
import traceback
import xml.etree.ElementTree as ETree
from urllib.parse import urlencode
from urllib.parse import urlparse

import requests
import xbmcgui  # pylint: disable=import-error
from core.common import get_platform_ip
from core.common import is_ip
from core.constants import CONFIG
from core.logger import Logger
from core.server_config import ServerConfigStore
from core.strings import i18n
from gui.dialogs.progress import ProgressDialog
from plex.discovery import PlexGDM
from plex.http import ACCOUNT_TIMEOUT
from plex.http import DIRECT_TIMEOUT
from plex.http import SIGN_IN_TIMEOUT
from plex.http import request as http_request
from plex.identity import METADATA_LANGUAGE_PROPERTY
from plex.identity import create_plex_identification
from plex.identity import get_client_identifier
from plex.section import PlexSection
from plex.server import PlexMediaServer
from plex.url import format_netloc
from plex.url import split_netloc
from storage.http_cache import CacheControl

DEFAULT_PORT = '32400'
LOG = Logger('plex')

WINDOW = xbmcgui.Window(10000)

# plex.tv account providers for Watchlist / Discover (not tied to a PMS)
PROVIDER_METADATA = 'https://metadata.provider.plex.tv'
PROVIDER_DISCOVER = 'https://discover.provider.plex.tv'
#: Guide and lineup of the free channels Plex serves itself
PROVIDER_EPG = 'https://epg.provider.plex.tv'

#: The Watchlist is handed out in pages; asked for in one go the provider still
#: answers with what it considers a container, so the pages are counted through.
WATCHLIST_PAGE_SIZE = 100
MAX_WATCHLIST_ITEMS = 2000


def _avatar_url(avatar):
    """Return a Kodi-friendly avatar URL, tolerating accounts without one."""
    avatar = avatar or ''
    if avatar.startswith('https://plex.tv') or avatar.startswith('http://plex.tv'):
        return avatar.replace('//', '//i2.wp.com/', 1)
    return avatar


class Plex:  # pylint: disable=too-many-public-methods, too-many-instance-attributes

    def __init__(self, settings, load=False):
        self.settings = settings
        # Provide an interface into Plex
        self.cache = CacheControl('servers', self.settings.cache())
        self.myplex_server = 'https://plex.tv'
        self.myplex_user = None
        self.myplex_token = None
        self.effective_user = None
        self.effective_token = None
        self.server_list = {}
        self.discovered = False
        self.server_list_cache = 'discovered_plex_servers.cache'
        self.plexhome_cache = 'plexhome_user.pcache'
        self.client_id = None
        self.user_list = {}
        self._provider_watchlist_ids = None
        self.plexhome_settings = {
            'myplex_signedin': False,
            'plexhome_enabled': False,
            'myplex_user_cache': '',
            'plexhome_user_cache': '',
            'plexhome_user_avatar': ''
        }

        self.server_configs = ServerConfigStore()

        self.setup_user_token()
        if load:
            self.load()

    def plex_identification_header(self):
        self.client_id = get_client_identifier(self.settings, self.client_id)
        return create_plex_identification(self.settings, client_id=self.client_id,
                                          token=self.effective_token)

    def is_plexhome_enabled(self):
        return self.plexhome_settings['plexhome_enabled']

    def is_myplex_signedin(self):
        return self.plexhome_settings['myplex_signedin']

    def get_myplex_user(self):
        return self.effective_user

    def get_myplex_avatar(self):
        return self.plexhome_settings['plexhome_user_avatar']

    def signout(self):
        self.plexhome_settings = {
            'myplex_signedin': False,
            'plexhome_enabled': False,
            'myplex_user_cache': '',
            'plexhome_user_cache': '',
            'plexhome_user_avatar': ''
        }

        self.delete_cache(True)
        LOG.debug('Signed out from myPlex')

    def get_signin_pin(self):
        data = self.talk_to_myplex('/pins.xml', method='post')
        try:
            xml = ETree.fromstring(data)
            code = xml.find('code').text
            identifier = xml.find('id').text
        except Exception:  # pylint: disable=broad-except
            code = None
            identifier = None

        if code is None:
            LOG.debug('Error, no code provided')
            code = '----'
            identifier = 'error'

        LOG.debug('code is: %s' % code)
        LOG.debug('id   is: %s' % identifier)

        return {
            'id': identifier,
            'code': list(code)
        }

    def check_signin_status(self, identifier):
        data = self.talk_to_myplex('/pins/%s.xml' % identifier, method='get2')
        xml = ETree.fromstring(data)
        temp_token = xml.find('auth_token').text

        LOG.debugplus('Temp token is: %s' % temp_token)

        if temp_token:
            try:
                response = http_request(
                    'get', '%s/users/account' % self.myplex_server,
                    params={'X-Plex-Token': temp_token},
                    headers=self.plex_identification_header(),
                    timeout=SIGN_IN_TIMEOUT)
            except requests.exceptions.RequestException as error:
                LOG.error('PIN sign in status request failed: %s' % error)
                return False
            response.encoding = 'utf-8'

            LOG.debug('Status Code: %s' % response.status_code)

            if response.status_code == 200:
                try:
                    LOG.debugplus(response.text)
                    LOG.debug('Received new plex token')
                    xml = ETree.fromstring(response.text)

                    home = xml.get('home', '0')
                    username = xml.get('username', '')
                    self.plexhome_settings['plexhome_user_avatar'] = \
                        _avatar_url(xml.get('thumb'))

                    if home == '1':
                        self.plexhome_settings['plexhome_enabled'] = True
                        LOG.debug('Setting Plex Home enabled.')
                    else:
                        self.plexhome_settings['plexhome_enabled'] = False
                        LOG.debug('Setting Plex Home disabled.')

                    token = xml.findtext('authentication-token')
                    self.plexhome_settings['myplex_user_cache'] = '%s|%s' % (username, token)
                    self.plexhome_settings['myplex_signedin'] = True
                    self.save_tokencache()
                    return True
                except Exception:  # pylint: disable=broad-except
                    LOG.debug('No authentication token found')

        return False

    def load(self):
        LOG.debug('Loading cached server list')

        data_ok = False
        self.server_list = None

        if WINDOW.getProperty('plugin.video.pyplexer-refresh.servers') != 'true':
            data_ok, self.server_list = self.cache.read_cache(self.server_list_cache)

        WINDOW.clearProperty('plugin.video.pyplexer-refresh.servers')

        if data_ok:
            if not self.check_server_version():
                LOG.debug('Refreshing for new versions')
                data_ok = False

            if not self.check_user():
                LOG.debug('User Switch, refreshing for new authorization settings')
                data_ok = False

        if not data_ok or not self.server_list:
            LOG.debug('unsuccessful')
            # fresh discovery: re-resolve the metadata language for the new list
            WINDOW.clearProperty(METADATA_LANGUAGE_PROPERTY)
            self.server_list = {}
            if not self.discover():
                self.server_list = {}

        LOG.debug('Server list is now: %s' % self.server_list)

        self._update_metadata_language()

    def setup_user_token(self):

        self.load_tokencache()

        if self.plexhome_settings['myplex_signedin']:
            LOG.debug('myPlex is logged in')
        else:
            return

        self.myplex_user, self.myplex_token = self.plexhome_settings['myplex_user_cache'].split('|')

        if self.plexhome_settings['plexhome_enabled']:
            LOG.debug('Plexhome is enabled')

        try:
            self.effective_user, self.effective_token = \
                self.plexhome_settings['plexhome_user_cache'].split('|')
        except Exception:  # pylint: disable=broad-except
            LOG.debug('No user set.  Will default to admin user')
            self.effective_user = self.myplex_user
            self.effective_token = self.myplex_token
            self.save_tokencache()

        myplex_user = self.myplex_user
        effective_user = self.effective_user
        if self.settings.privacy():
            myplex_user = hashlib.md5()
            myplex_user.update(self.myplex_user.encode('utf-8'))
            myplex_user = myplex_user.hexdigest()

            effective_user = hashlib.md5()
            effective_user.update(self.effective_user.encode('utf-8'))
            effective_user = effective_user.hexdigest()

        LOG.debug('myPlex user id: %s' % myplex_user)
        LOG.debug('Effective user id: %s' % effective_user)

    def load_tokencache(self):

        data_ok, token_cache = self.cache.read_cache(self.plexhome_cache)

        if data_ok:
            try:
                if not isinstance(token_cache['myplex_signedin'], int):
                    raise TypeError
                if not isinstance(token_cache['plexhome_enabled'], int):
                    raise TypeError
                if not isinstance(token_cache['myplex_user_cache'], str):
                    raise TypeError
                if not isinstance(token_cache['plexhome_user_cache'], str):
                    raise TypeError
                if not isinstance(token_cache['plexhome_user_avatar'], str):
                    raise TypeError

                self.plexhome_settings = token_cache
                LOG.debug('plexhome_cache data loaded successfully')
            except Exception:  # pylint: disable=broad-except
                LOG.debug('plexhome_cache data is corrupt. Will not use.')
        else:
            LOG.debug('plexhome cache data not loaded')

    def save_tokencache(self):
        self.cache.write_cache(self.plexhome_cache, self.plexhome_settings)

    def check_server_version(self):
        for _uuid, servers in self.server_list.items():
            try:
                if not servers.get_revision() == CONFIG['required_revision']:
                    LOG.debug('Old object revision found')
                    return False
            except Exception:  # pylint: disable=broad-except
                LOG.debug('No revision found')
                return False
        return True

    def check_user(self):

        if self.effective_user is None:
            return True

        for _uuid, servers in self.server_list.items():
            if not servers.get_user() == self.effective_user:
                LOG.debug('authorized user mismatch')
                return False
        return True

    def discover(self):
        self.discover_all_servers()

        if self.server_list:
            self.discovered = True

        return self.discovered

    def get_server_list(self):
        return self.server_list.values()

    def get_active_server_list(self):
        """The servers to browse: the chosen one, or all when none is chosen.

        A server that was picked and has since gone away must not leave the
        add-on with an empty menu, so an unknown choice falls back to all.
        """
        chosen = self.settings.active_server()
        if not chosen:
            return self.get_server_list()

        servers = [server for server in self.get_server_list()
                   if server.get_uuid() == chosen]
        if servers:
            return servers

        LOG.debug('Chosen server %s is not among the known ones, showing all' % chosen)
        return self.get_server_list()

    def active_sections(self):
        """``all_sections`` limited to the server being browsed."""
        sections = self.all_sections()

        chosen = self.settings.active_server()
        if not chosen:
            return sections

        return [section for section in sections
                if section.get_server_uuid() == chosen] or sections

    def active_server_name(self):
        """The name of the chosen server, empty while browsing all of them."""
        chosen = self.settings.active_server()
        for server in self.get_server_list():
            if server.get_uuid() == chosen:
                return server.get_name()
        return ''

    def talk_direct_to_server(self, ip_address='localhost', port=DEFAULT_PORT, url=None):
        uri = 'http://%s%s' % (format_netloc(ip_address, port), url or '')
        try:
            response = http_request('get', uri, params=self.plex_identification_header(),
                                    timeout=DIRECT_TIMEOUT)
        except requests.exceptions.RequestException as error:
            LOG.debug('Direct server request failed for %s: %s' % (uri, error))
            return ''
        response.encoding = 'utf-8'

        LOG.debug('URL was: %s' % response.url)

        if response.status_code == requests.codes.ok:  # pylint: disable=no-member
            LOG.debugplus('XML: \n%s' % response.text)
            return response.text

        return ''

    def get_processed_myplex_xml(self, url):
        data = self.talk_to_myplex(url)
        return ETree.fromstring(data)

    def gdm_discovery(self):
        try:
            interface_address = get_platform_ip()
            LOG.debug('Using interface: %s for GDM discovery' % interface_address)
        except Exception:  # pylint: disable=broad-except
            interface_address = None
            LOG.debug('Using systems default interface for GDM discovery')

        try:
            gdm_client = PlexGDM(interface=interface_address)
            gdm_client.discover()
            gdm_server_name = gdm_client.get_server_list()
        except Exception as error:  # pylint: disable=broad-except
            LOG.error('GDM Issue [%s]' % error)
            traceback.print_exc()
        else:
            if gdm_client.discovery_complete and gdm_server_name:
                LOG.debug('GDM discovery completed')

                for device in gdm_server_name:
                    server = PlexMediaServer(name=device['serverName'],
                                             address=device['server'],
                                             port=device['port'],
                                             discovery='discovery',
                                             server_uuid=device['uuid'])
                    server.set_user(self.effective_user)
                    server.set_token(self.effective_token)

                    self.merge_server(server)
            else:
                LOG.debug('GDM was not able to discover any servers')

    def user_provided_discovery(self):
        port = self.settings.port()
        if not port:
            LOG.debug('No port defined.  Using default of ' + DEFAULT_PORT)
            port = DEFAULT_PORT

        ip_address = self.settings.ip_address()
        LOG.debug('Settings hostname and port: %s : %s' %
                  (ip_address, port))

        server = PlexMediaServer(address=ip_address, port=port, discovery='local')
        server.set_user(self.effective_user)
        server.set_token(self.effective_token)
        server.set_protocol('https' if self.settings.https() else 'http')
        server.ssl_certificate_verification = self.settings.certificate_verification()
        server.refresh()

        if server.discovered:
            self.merge_server(server)
        else:
            LOG.error('Error: Unable to discover server %s' %
                      self.settings.ip_address())

    def _discovery_notification(self, servers):
        if self.settings.servers_detected_notification():
            if servers:
                msg = i18n('Found servers:') + ' ' + servers
            else:
                msg = i18n('No servers found')

            xbmcgui.Dialog().notification(heading=CONFIG['name'],
                                          message=msg,
                                          icon=CONFIG['icon'],
                                          sound=False)

    def discover_all_servers(self):
        with ProgressDialog(heading=CONFIG['name'] + ' ' + i18n('Server Discovery'),
                            line1=i18n('Please wait...'), background=True) as progress_dialog:
            try:
                percent = 0
                self.server_list = {}
                # First discover the servers we should know about from myplex
                if self.is_myplex_signedin():
                    LOG.debug('Adding myPlex as a server location')
                    progress_dialog.update(percent=percent, line1=i18n('myPlex discovery...'))

                    self.server_list = self.get_myplex_servers()

                    if self.server_list:
                        LOG.debug('MyPlex discovery completed successfully')
                    else:
                        LOG.debug('MyPlex discovery found no servers')

                # Now grab any local devices we can find
                if self.settings.discovery() == '1':
                    LOG.debug('local GDM discovery setting enabled.')
                    LOG.debug('Attempting GDM lookup on multicast')
                    percent += 40
                    progress_dialog.update(percent=percent, line1=i18n('GDM discovery...'))
                    self.gdm_discovery()

                # Get any manually configured servers
                elif self.settings.ip_address():
                    percent += 40
                    progress_dialog.update(percent=percent, line1=i18n('User provided...'))
                    self.user_provided_discovery()

                percent += 40
                progress_dialog.update(percent=percent, line1=i18n('Caching results...'))

                for server_uuid in list(self.server_list.keys()):
                    self.server_list[server_uuid].settings = None  # can't pickle xbmcaddon.Addon()

                self.cache.write_cache(self.server_list_cache, self.server_list)

                servers = list(map(lambda x: (self.server_list[x].get_name(), x),
                                   self.server_list.keys()))

                server_names = ', '.join(map(lambda x: x[0], servers))

                LOG.debug('serverList is: %s ' % servers)
            finally:
                progress_dialog.update(percent=100, line1=i18n('Finished'))

        self._discovery_notification(server_names)

    def get_myplex_queue(self, start=0, size=0):
        path = '/pms/playlists/queue/all'
        if size > 0:
            path = '%s?%s' % (path, urlencode({
                'X-Plex-Container-Start': start,
                'X-Plex-Container-Size': size,
            }))
        return self.get_processed_myplex_xml(path)

    def get_provider_token(self):
        return self.effective_token

    def resolve_metadata_language(self):
        """Determine the metadata language configured on the user's Plex Media
        Server libraries and cache it (per Kodi session) in a window property so
        every X-Plex-Language header uses it. Prefers a movie/TV library; falls
        back to English when nothing can be determined."""
        cached = WINDOW.getProperty(METADATA_LANGUAGE_PROPERTY)
        if cached:
            return cached

        language = ''
        fallback = ''
        try:
            for server in self.get_server_list():
                if server.is_offline() or server.is_secondary():
                    continue
                for section in server.get_sections():
                    section_language = section.get_language()
                    if not section_language:
                        continue
                    if not fallback:
                        fallback = section_language
                    if section.is_movie() or section.is_show():
                        language = section_language
                        break
                if language:
                    break
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('Could not determine PMS metadata language: %s' % error)

        resolved = language or fallback
        if resolved:
            WINDOW.setProperty(METADATA_LANGUAGE_PROPERTY, resolved)
            LOG.debug('Metadata language resolved to: %s' % resolved)
            return resolved

        return 'en'

    def _update_metadata_language(self):
        """Resolve the PMS language and rebuild each server's cached
        identification header so server requests use it too."""
        self.resolve_metadata_language()
        for server in self.get_server_list():
            try:
                server.update_identification()
            except Exception as error:  # pylint: disable=broad-except
                LOG.debug('Could not refresh identification: %s' % error)

    def talk_to_provider(self, base, path):
        """Talk to a plex.tv account provider (metadata/discover) using the
        account token + identification headers. Returns the raw XML text or None.
        """
        if not self.plexhome_settings['myplex_signedin']:
            LOG.debug('Provider request skipped, not signed into myPlex')
            return None

        url = '%s%s' % (base, path)
        LOG.debug('provider url = %s' % url)

        try:
            response = http_request('get', url, params=self.plex_identification_header(),
                                    headers={'Accept': 'application/xml'},
                                    verify=True, timeout=ACCOUNT_TIMEOUT)
        except requests.exceptions.RequestException as error:
            LOG.error('provider request failed for %s: %s' % (url, error))
            return None

        response.encoding = 'utf-8'
        if response.status_code >= 400:
            LOG.error('provider HTTP error %s for %s' % (response.status_code, url))
            LOG.debug('provider error body: %s' % response.text[:500])
            return None

        return response.text

    def provider_xml(self, base, path):
        """Fetch one provider path, parsed; None when it does not answer."""
        return self._parse_provider_xml(self.talk_to_provider(base, path))

    @staticmethod
    def _parse_provider_xml(data):
        if not data:
            return None
        try:
            return ETree.fromstring(data)
        except ETree.ParseError as error:
            LOG.error('Unable to parse provider response: %s' % error)
            return None

    def get_watchlist(self, path=None):
        """The whole Watchlist, not just its first page.

        The provider hands out a container of twenty at a time and says in
        ``totalSize`` how many there are; the pages are collected into one
        container so the listing shows everything at once.
        """
        if path is not None:
            return self._parse_provider_xml(self.talk_to_provider(PROVIDER_DISCOVER, path))

        path = '/library/sections/watchlist/all' \
               '?includeCollections=1&includeExternalMedia=1'

        container = None
        start = 0

        while start < MAX_WATCHLIST_ITEMS:
            page = self._parse_provider_xml(self.talk_to_provider(
                PROVIDER_DISCOVER, '%s&X-Plex-Container-Start=%s&X-Plex-Container-Size=%s' %
                (path, start, WATCHLIST_PAGE_SIZE)))

            if page is None:
                break

            children = list(page)
            if container is None:
                container = page
            else:
                for child in children:
                    container.append(child)

            start += len(children)

            try:
                total = int(page.get('totalSize') or 0)
            except (TypeError, ValueError):
                total = 0

            if not children or (total and start >= total):
                break
            if not total and len(children) < WATCHLIST_PAGE_SIZE:
                break  # nothing says how many there are, and the page was short

        if container is not None:
            container.set('size', str(len(list(container))))
            LOG.debug('Watchlist holds %s item(s)' % len(list(container)))

        return container

    def get_provider_metadata(self, base, rating_keys):
        """Metadata of one or several provider items, rating keys separated by
        commas - the listings leave out fields the metadata carries.

        The answer is a container like any other and is cut to twenty unless it
        is told how many items are being asked for.
        """
        if not rating_keys:
            return None

        wanted = len(rating_keys.split(','))

        data = self.talk_to_provider(
            base, '/library/metadata/%s?includeGuids=1&X-Plex-Container-Start=0'
                  '&X-Plex-Container-Size=%s' % (rating_keys, wanted))

        return self._parse_provider_xml(data)

    def resolve_provider_rating_key(self, external_guid, media_type):
        """Resolve a TMDb/IMDb/TVDb guid to a Plex Discover rating key.

        Plex's Watchlist actions do not accept external ids. The matches
        endpoint translates them to the global provider rating key. Supplying
        the media type is essential because TMDb movie and show ids share the
        same numeric namespace.
        """
        external_guid = str(external_guid or '').strip()
        media_type = str(media_type or '').strip().lower()
        plex_type = {'movie': 1, 'show': 2}.get(media_type)
        if not plex_type or not external_guid:
            return None

        path = '/library/metadata/matches?%s' % urlencode({
            'type': plex_type,
            'guid': external_guid,
        })
        tree = self._parse_provider_xml(self.talk_to_provider(PROVIDER_METADATA, path))
        if tree is None:
            return None

        for element in tree.iter():
            rating_key = element.get('ratingKey')
            if rating_key:
                LOG.debug('Provider match %s -> ratingKey %s' %
                          (external_guid, rating_key))
                return rating_key

        LOG.debug('No provider match for %s (%s)' % (external_guid, media_type))
        return None

    def is_provider_watchlisted(self, rating_key):
        """Return whether a Discover rating key is already on the Watchlist."""
        if not rating_key:
            return None

        return str(rating_key) in self.get_provider_watchlist_ids()

    def get_provider_watchlist_ids(self):
        """Return all provider ids on the Watchlist, fetched only once."""
        if self._provider_watchlist_ids is not None:
            return self._provider_watchlist_ids

        ids = set()
        tree = self.get_watchlist()
        if tree is not None:
            for element in tree.iter():
                candidate = element.get('ratingKey')
                guid = element.get('guid') or ''
                if candidate:
                    ids.add(str(candidate))
                if guid:
                    ids.add(guid.rsplit('/', 1)[-1])

        self._provider_watchlist_ids = ids
        return ids

    def _update_provider_watchlist_ids(self, add, rating_key):
        if self._provider_watchlist_ids is None:
            return

        wanted = str(rating_key)
        if add:
            self._provider_watchlist_ids.add(wanted)
        else:
            self._provider_watchlist_ids.discard(wanted)

    def get_discover_hubs(self):
        """The account-level Plex Discover feed."""
        tree = self._parse_provider_xml(self.talk_to_provider(PROVIDER_DISCOVER, '/hubs'))
        if tree is not None and len(list(tree)):
            return tree
        return None

    def provider_watchlist_action(self, add, rating_key):
        """Add or remove a title from the account Watchlist. `rating_key` is the
        item's Discover metadata ratingKey. Tries both account providers."""
        if not self.plexhome_settings['myplex_signedin'] or not rating_key:
            return False

        action = 'addToWatchlist' if add else 'removeFromWatchlist'

        for base in (PROVIDER_METADATA, PROVIDER_DISCOVER):
            url = '%s/actions/%s' % (base, action)
            params = self.plex_identification_header()
            params['ratingKey'] = rating_key

            LOG.debug('Watchlist action %s at %s for ratingKey %s' %
                      (action, base, rating_key))
            try:
                response = http_request('put', url, params=params, verify=True,
                                        timeout=ACCOUNT_TIMEOUT)
            except requests.exceptions.RequestException as error:
                LOG.error('Watchlist action failed at %s: %s' % (base, error))
                continue

            if response.status_code < 400:
                self._update_provider_watchlist_ids(add, rating_key)
                return True

            LOG.error('Watchlist action HTTP %s at %s: %s' %
                      (response.status_code, base, response.text[:300]))

        return False

    def get_provider_tree(self, full_url):
        """Fetch and parse an absolute provider URL (used to drill into items)."""
        parts = urlparse(full_url)
        base = '%s://%s' % (parts.scheme, parts.netloc)
        path = full_url[len(base):]
        data = self.talk_to_provider(base, path)
        return self._parse_provider_xml(data)

    def get_myplex_sections(self):
        xml = self.talk_to_myplex('/pms/system/library/sections')
        if xml is False:
            return {}
        return xml

    def get_myplex_servers(self):
        temp_servers = {}
        xml = self.talk_to_myplex('/api/resources?includeHttps=1')

        if xml is False:
            return {}

        server_list = ETree.fromstring(xml)
        devices = server_list.iter('Device')

        for device in devices:

            LOG.debug('[%s] Found device' % device.get('name'))

            if 'server' not in device.get('provides'):
                LOG.debug('[%s] Skipping as not a server [%s]' %
                          (device.get('name'), device.get('provides')))
                continue

            discovered_server = PlexMediaServer(name=device.get('name'),
                                                discovery='myplex')
            discovered_server.set_uuid(device.get('clientIdentifier'))
            discovered_server.set_owned(device.get('owned'))
            discovered_server.set_token(device.get('accessToken'))
            discovered_server.set_user(self.effective_user)
            connections = device.iter('Connection')

            for connection in connections:
                LOG.debug('[%s] Found server connection' % device.get('name'))

                if connection.get('local') == '0':
                    discovered_server.add_external_connection(connection.get('address'),
                                                              connection.get('port'),
                                                              connection.get('uri'))
                else:
                    discovered_server.add_internal_connection(connection.get('address'),
                                                              connection.get('port'),
                                                              connection.get('uri'))

                if connection.get('protocol') == 'http':
                    LOG.debug('[%s] Dropping back to http' % device.get('name'))
                    discovered_server.set_protocol('http')

            discovered_server.add_custom_access_urls(
                self.server_configs.access_urls(device.get('clientIdentifier'))
            )

            discovered_server.ssl_certificate_verification = \
                self.server_configs.ssl_certificate_verification(device.get('clientIdentifier'))

            discovered_server.set_best_address()  # Default to external address

            temp_servers[discovered_server.get_uuid()] = discovered_server
            LOG.debug('[%s] Discovered server via myPlex: %s' %
                      (discovered_server.get_name(), discovered_server.get_uuid()))

        return temp_servers

    def merge_server(self, server):
        LOG.debug('merging server with uuid %s' % server.get_uuid())

        # Only the plex.tv discovery attached these; a server found over the
        # network or entered by hand never saw its own access urls, so the one
        # address that would have reached it was left untested.
        server.add_custom_access_urls(self.server_configs.access_urls(server.get_uuid()))

        try:
            existing = self.get_server_from_uuid(server.get_uuid())
        except Exception:  # pylint: disable=broad-except
            LOG.debug('Adding new server %s %s' %
                      (server.get_name(), server.get_uuid()))
            server.refresh()
            if server.discovered:
                self.server_list[server.get_uuid()] = server
        else:
            LOG.debug('Found existing server %s %s' %
                      (existing.get_name(), existing.get_uuid()))

            existing.add_custom_access_urls(
                self.server_configs.access_urls(existing.get_uuid()))
            existing.set_best_address(server.get_access_address())
            existing.refresh()
            self.server_list[existing.get_uuid()] = existing

    def _request(self, path, method, use_params):
        try:
            if use_params:
                response = http_request(method, '%s%s' % (self.myplex_server, path),
                                        params=self.plex_identification_header(),
                                        verify=True, timeout=ACCOUNT_TIMEOUT)
            else:
                response = http_request(method, '%s%s' % (self.myplex_server, path),
                                        headers=self.plex_identification_header(),
                                        verify=True, timeout=ACCOUNT_TIMEOUT)
        except ValueError:
            LOG.error('Unknown HTTP method requested: %s' % method)
            response = None

        if response:
            response.encoding = 'utf-8'

        return response

    def talk_to_myplex(self, path, renew=False, method='get'):
        # ``renew`` is retained for callers using the old signature. Plex
        # tokens cannot be refreshed without credentials, so a 401 is returned
        # as unauthorized instead of repeating the identical request.
        _ = renew
        LOG.debug('url = %s%s' % (self.myplex_server, path))

        use_params = method == 'get'
        method = method.replace('get2', 'get')

        try:  # pylint: disable=no-else-return
            response = self._request(path, method, use_params=use_params)

        except requests.exceptions.RequestException as error:
            LOG.error('myPlex request failed for %s on %s: %s' %
                      (self.myplex_server, path, error))
            return '<?xml version="1.0" encoding="UTF-8"?><message status="error"></message>'

        else:
            if response is None:
                return '<?xml version="1.0" encoding="UTF-8"?>' \
                       '<message status="error"></message>'
            LOG.debugplus('Full URL was: %s' % response.url)
            LOG.debugplus('Full header sent was: %s' % response.request.headers)
            LOG.debugplus('Full header received was: %s' % response.headers)

            if response.status_code >= 400:
                error = 'HTTP response error: %s' % response.status_code
                LOG.error(error)
                if response.status_code in (401, 403, 404):
                    return '<?xml version="1.0" encoding="UTF-8"?>' \
                           '<message status="unauthorized">' \
                           '</message>'

                return '<?xml version="1.0" encoding="UTF-8"?>' \
                       '<message status="error">' \
                       '</message>'

            LOG.debugplus('XML: \n%s' % response.text)
            link = response.text.encode('utf-8')

        return link

    def get_myplex_token(self):

        if self.plexhome_settings['myplex_signedin']:
            return {
                'X-Plex-Token': self.effective_token
            }

        LOG.debug('Myplex not in use')
        return {}

    def sign_into_myplex(self, username=None, password=None):
        LOG.debug('Getting New token')

        if username is None:
            LOG.debug('No myPlex details in provided..')
            return None

        credentials = '%s:%s' % (username, password)
        credentials = credentials.encode('utf-8')
        base64bytes = base64.encodebytes(credentials)
        base64string = base64bytes.decode('utf-8').replace('\n', '')

        token = False
        myplex_headers = {
            'Authorization': 'Basic %s' % base64string
        }

        try:
            response = http_request(
                'post', '%s/users/sign_in.xml' % self.myplex_server,
                headers=dict(self.plex_identification_header(), **myplex_headers),
                verify=True, timeout=SIGN_IN_TIMEOUT)
        except requests.exceptions.RequestException as error:
            LOG.error('myPlex sign in request failed: %s' % error)
            return None
        response.encoding = 'utf-8'

        if response.status_code == 201:
            try:
                LOG.debugplus(response.text)
                LOG.debug('Received new plex token')
                xml = ETree.fromstring(response.text)
                home = xml.get('home', '0')

                self.plexhome_settings['plexhome_user_avatar'] = \
                    _avatar_url(xml.get('thumb'))

                if home == '1':
                    self.plexhome_settings['plexhome_enabled'] = True
                    LOG.debug('Setting Plex Home enabled.')
                else:
                    self.plexhome_settings['plexhome_enabled'] = False
                    LOG.debug('Setting Plex Home disabled.')

                token = xml.findtext('authentication-token')
                self.plexhome_settings['myplex_user_cache'] = '%s|%s' % (username, token)
                self.plexhome_settings['myplex_signedin'] = True
                self.save_tokencache()
            except Exception:  # pylint: disable=broad-except
                LOG.debug('No authentication token found')
        else:
            error = 'HTTP response error: %s %s' % (response.status_code, response.reason)
            LOG.error(error)
            return None

        return token

    def get_server_from_parts(self, scheme, uri):
        LOG.debug('IP to lookup: %s' % uri)

        uri, port = split_netloc(uri)

        if is_ip(uri):
            LOG.debug('IP address detected - passing through')
        else:
            try:
                socket.gethostbyname(uri)
            except Exception:  # pylint: disable=broad-except
                LOG.debug('Unable to lookup hostname: %s' % uri)
                return PlexMediaServer(name='dummy', address='127.0.0.1',
                                       port=32400, discovery='local')

        server_list = self.server_list.values()
        for server in server_list:

            LOG.debug('[%s] - checking ip:%s against server ip %s' %
                      (server.get_name(), uri, server.get_address()))

            if server.find_address_match(scheme, uri, port):
                return server

        LOG.debug('Unable to translate - Returning new plex server set to %s' % uri)

        return PlexMediaServer(name=i18n('Unknown'), address=uri, port=port, discovery='local')

    def get_server_from_url(self, url):
        url_parts = urlparse(url)
        return self.get_server_from_parts(url_parts.scheme, url_parts.netloc)

    def get_server_from_uuid(self, _uuid):
        return self.server_list[_uuid]

    def get_processed_xml(self, url):
        url_parts = urlparse(url)
        server = self.get_server_from_parts(url_parts.scheme, url_parts.netloc)

        if server:
            return server.processed_xml(url)
        return ''

    def talk_to_server(self, url):
        url_parts = urlparse(url)
        server = self.get_server_from_parts(url_parts.scheme, url_parts.netloc)

        if server:
            return server.raw_xml(url)
        return ''

    def delete_cache(self, force=False):
        return self.cache.delete_cache(force)

    def set_plex_home_users(self):
        data = ETree.fromstring(self.talk_to_myplex('/api/home/users'))
        self.user_list = {}
        for users in data:
            add = {
                'id': users.get('id'),
                'admin': users.get('admin'),
                'restricted': users.get('restricted'),
                'protected': users.get('protected'),
                'title': users.get('title'),
                'username': users.get('username'),
                'email': users.get('email'),
                'thumb': users.get('thumb')
            }
            self.user_list[users.get('id')] = add

    def get_plex_home_users(self):
        data = ETree.fromstring(self.talk_to_myplex('/api/home/users'))
        self.user_list = {}
        for users in data:
            add = {
                'id': users.get('id'),
                'admin': users.get('admin'),
                'restricted': users.get('restricted'),
                'protected': users.get('protected'),
                'title': users.get('title'),
                'username': users.get('username'),
                'email': users.get('email'),
                'thumb': users.get('thumb')
            }
            self.user_list[users.get('title')] = add

        return self.user_list

    def switch_plex_home_user(self, uid, pin):
        if pin is None:
            pin_arg = '?X-Plex-Token=%s' % self.effective_token
        else:
            pin_arg = '?pin=%s&X-Plex-Token=%s' % (pin, self.effective_token)

        data = self.talk_to_myplex('/api/home/users/%s/switch%s' % (uid, pin_arg), method='post')
        tree = ETree.fromstring(data)

        if tree.get('status') == 'unauthorized':
            return False, 'Unauthorised'

        if tree.get('status') == 'error':
            return False, 'Unknown error'

        username = None
        user_list = self.user_list.values()
        for users in user_list:
            if uid == users['id']:
                username = users['title']
                break

        self.plexhome_settings['plexhome_user_avatar'] = _avatar_url(tree.get('thumb'))

        token = tree.findtext('authentication-token')
        self.plexhome_settings['plexhome_user_cache'] = '%s|%s' % (username, token)
        self.effective_user = username
        self.save_tokencache()
        return True, None

    def is_admin(self):
        if self.effective_user == self.myplex_user:
            return True
        return False

    def get_myplex_information(self):
        data = self.talk_to_myplex('/users/account')
        xml = ETree.fromstring(data)

        result = {
            'username': xml.get('username', 'unknown'),
            'email': xml.get('email', 'unknown'),
            'thumb': xml.get('thumb')
        }

        subscription = xml.find('subscription')
        if subscription is not None:
            result['plexpass'] = subscription.get('plan')
        else:
            result['plexpass'] = 'No Subscription'

        try:
            date = xml.find('joined-at').text
            result['membersince'] = date.split(' ')[0]
        except Exception:  # pylint: disable=broad-except
            result['membersince'] = i18n('Unknown')

        LOG.debug('Gathered information: %s' % result)

        return result

    def all_sections(self):
        tree = ETree.fromstring(self.get_myplex_sections())
        return list(map(PlexSection, tree))

    @staticmethod
    def _tree_tostring(tree):
        return ETree.tostring(tree)
