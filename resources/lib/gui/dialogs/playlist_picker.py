# -*- coding: utf-8 -*-

import random
from itertools import chain
from itertools import groupby
from itertools import zip_longest

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.constants import CONFIG
from core.context import Item
from core.logger import Logger
from core.strings import i18n
from gui.builders.episode import create_episode_item
from gui.builders.movie import create_movie_item
from gui.dialogs.progress import ProgressDialog

ACTIVE_DIALOG_PROPERTY = '-'.join([CONFIG['id'], 'dialog_active'])

LOG = Logger('pyplexer_playlist')


class PlaylistConfigurator:
    """Native, skin-styled configuration flow for the combined playlist.

    Instead of a custom pyxbmct window this uses Kodi's own select/multiselect
    dialogs, so the screen fully inherits the active skin's design. The menu
    behaves like a small settings screen: each row shows its current value and
    can be edited, and the final row generates and plays the playlist.
    """

    def __init__(self, context):
        self.context = context
        self.dialog = xbmcgui.Dialog()
        self._menu_pos = 0

        self._content_types = [
            (i18n('Movies'), 'movies'),
            (i18n('TV Shows'), 'tvshows'),
            (i18n('Mixed'), 'mixed'),
        ]
        self._sources = [
            (i18n('All'), 'all'),
            (i18n('On Deck'), 'on_deck'),
            (i18n('Recently Added'), 'recent_added'),
            (i18n('Recently Released'), 'recent_released'),
        ]
        self._item_counts = [1, 5, 10, 25, 50, 100, 250, 500, 1000]
        self._servers = self._load_servers()

        self.data = {
            'content': 'tvshows',
            'item_count': 50,
            'servers': [(i18n('All Servers'), None)],
            'source': (i18n('On Deck'), 'on_deck'),
            'shuffle': False,
        }

    def _load_servers(self):
        servers = [(i18n('All Servers'), None)]
        for server in self.context.plex_network.get_server_list():
            name = server.get_name()
            uuid = server.get_uuid()
            if name and uuid:
                servers.append((name, uuid))
        return servers

    # -- label helpers ---------------------------------------------------

    @staticmethod
    def _label(string_id, fallback):
        # Kodi caches an add-on's strings.po per session, so a newly added
        # string id can return empty until the next restart -> use a fallback
        text = i18n(string_id)
        return text if text else fallback

    @staticmethod
    def _row(label, value):
        return '[B]%s:[/B] %s' % (label, value)

    def _content_label(self):
        for name, value in self._content_types:
            if value == self.data['content']:
                return name
        return ''

    def _servers_label(self):
        names = [name for name, _ in self.data.get('servers', [])]
        return ', '.join(names) if names else i18n('All Servers')

    @staticmethod
    def _bool_label(value):
        return '[X]' if value else '[ ]'

    def _menu_entries(self):
        return [
            self._row(self._label('Content', 'Inhalt'), self._content_label()),
            self._row(i18n('Item Count'), self.data['item_count']),
            self._row(i18n('Server(s)'), self._servers_label()),
            self._row(i18n('Source'), self.data['source'][0]),
            self._row(i18n('Shuffle'), self._bool_label(self.data['shuffle'])),
            '[B]▶ %s[/B]' % i18n('Play'),
        ]

    # -- run loop --------------------------------------------------------

    def run(self):
        xbmc.executebuiltin('Dialog.Close(all,true)')

        while True:
            choice = self.dialog.select(i18n('PyPlexer Playlist'), self._menu_entries(),
                                        preselect=self._menu_pos)

            if choice == -1:
                return False

            self._menu_pos = choice

            if choice == 0:
                self._choose_content()
            elif choice == 1:
                self._choose_count()
            elif choice == 2:
                self._choose_servers()
            elif choice == 3:
                self._choose_source()
            elif choice == 4:
                self.data['shuffle'] = not self.data['shuffle']
            elif choice == 5:
                if self._play():
                    return True

    # -- individual settings --------------------------------------------

    def _choose_content(self):
        labels = [name for name, _ in self._content_types]
        preselect = next((i for i, (_, value) in enumerate(self._content_types)
                          if value == self.data['content']), 0)
        choice = self.dialog.select(self._label('Content', 'Inhalt'), labels, preselect=preselect)
        if choice != -1:
            self.data['content'] = self._content_types[choice][1]

    def _choose_count(self):
        labels = [str(count) for count in self._item_counts]
        try:
            preselect = self._item_counts.index(self.data['item_count'])
        except ValueError:
            preselect = 0
        choice = self.dialog.select(i18n('Item Count'), labels, preselect=preselect)
        if choice != -1:
            self.data['item_count'] = self._item_counts[choice]

    def _choose_source(self):
        labels = [name for name, _ in self._sources]
        preselect = next((i for i, (_, value) in enumerate(self._sources)
                          if value == self.data['source'][1]), 0)
        choice = self.dialog.select(i18n('Source'), labels, preselect=preselect)
        if choice != -1:
            self.data['source'] = self._sources[choice]

    def _choose_servers(self):
        labels = [name for name, _ in self._servers]
        current = self.data.get('servers', [])
        preselect = [i for i, entry in enumerate(self._servers) if entry in current]

        selected = self.dialog.multiselect(i18n('Server(s)'), labels, preselect=preselect)
        if selected is None:
            return

        # "All Servers" (index 0) or an empty selection falls back to all servers
        if not selected or 0 in selected:
            self.data['servers'] = [(i18n('All Servers'), None)]
        else:
            self.data['servers'] = [self._servers[index] for index in selected]

    def _play(self):
        generator = PlaylistGenerator(context=self.context, data=self.data)
        return bool(generator.generate())


class PlaylistGenerator:

    def __init__(self, context, data):
        self.context = context
        self.data = data

        self.plex_network = context.plex_network

        self._content = data['content']
        self._item_count = data['item_count']
        self._servers = data['servers']
        self._source = data['source'][1]
        self._shuffle = data['shuffle']
        LOG.debug('PlaylistGenerator initialized: content=%s, item_count=%d, '
                  'servers=%s, source=%s, shuffle=%s' %
                  (self.content, self.item_count, self.servers,
                   self.source, str(self.shuffle)))

    @property
    def content(self):
        return self._content

    @property
    def item_count(self):
        return int(self._item_count)

    @property
    def servers(self):
        return self._servers

    @property
    def source(self):
        return self._source

    @property
    def shuffle(self):
        return bool(self._shuffle)

    @property
    def content_types(self):
        return ['tvshows', 'movies'] if self.content == 'mixed' else [self.content]

    def generate(self):
        with ProgressDialog(i18n('Generating Playlist'), i18n('This may take a while...')) as \
                progress_dialog:

            progress_dialog.update(0, i18n('Retrieving server list...'))
            servers = self._get_servers()
            if progress_dialog.is_canceled():
                return None

            progress_dialog.update(10, i18n('Retrieving server sections...'))
            sections = self._get_sections(servers, progress_dialog)
            if progress_dialog.is_canceled():
                return None

            progress_dialog.update(20, i18n('Retrieving content metadata...'))
            item_collections = self._get_item_collections(sections, progress_dialog)
            if progress_dialog.is_canceled():
                return None

            progress_dialog.update(60, i18n('Retrieving final sample...'))
            items = self._get_sample(item_collections)
            if progress_dialog.is_canceled():
                return None

            progress_dialog.update(70, i18n('Adding items to playlist...'))
            playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
            playlist.clear()

            _divisor, _percent_value = self._get_progress_data(items, 29)
            _percent = progress_dialog.percent

            for index, item in enumerate(items):
                if progress_dialog.is_canceled():
                    return None

                if index % _divisor == 0:
                    _percent += _percent_value
                progress_dialog.update(_percent,
                                       i18n('Adding %s to playlist...') % item[1].getLabel())

                playlist.add(*item)

            if progress_dialog.is_canceled():
                return None

            progress_dialog.update(100, i18n('Completed.'))
            xbmc.sleep(500)
            return items[0]

    def _get_progress_data(self, items, percent):
        item_count = len(items)
        _divisor = self._limiter(int(item_count // percent), lower_limit=1)
        _percent_value = self._limiter(int(percent // item_count), lower_limit=1)
        return _divisor, _percent_value

    def _get_servers(self):
        if len(self.servers) == 1 and self.servers[0][1] is None:
            return self.plex_network.get_server_list()

        return [self.plex_network.get_server_from_uuid(uuid)
                for _, uuid in self.servers if uuid is not None]

    def _get_sections(self, servers, dialog):
        server_sections = []
        for server in servers:
            sections = server.get_sections()

            _divisor, _percent_value = self._get_progress_data(sections, 4)
            _percent = dialog.percent

            for index, section in enumerate(sections):
                if dialog.is_canceled():
                    return None

                if index % _divisor == 0:
                    _percent += _percent_value
                dialog.update(_percent, i18n('Checking section %s on %s...') %
                              (section.get_title(), server.get_name()))

                if section.content_type() in self.content_types:
                    server_sections.append((server, section))

        return server_sections

    def _get_item_collection(self, server, tree):
        branches = tree.iter('Video')

        if branches is None:
            return []

        if tree.get('viewGroup') == 'show':
            branches = self._get_distributed_tvshows(branches)

        item_collection = []
        for content in branches:
            item = Item(server, server.get_url_location(), tree, content, up_next=False)
            if content.get('type') == 'episode':
                item_collection.append((server, create_episode_item(self.context, item)))
            elif content.get('type') == 'movie':
                item_collection.append((server, create_movie_item(self.context, item)))

        return item_collection

    def _get_item_collections(self, sections, dialog):
        _trees = self._get_section_trees(sections, dialog)
        if not _trees:
            return []

        server_collections = self._get_distributed_by_server(_trees)

        _divisor, _percent_value = self._get_progress_data(server_collections, 4)
        _percent = dialog.percent

        _index = 0
        item_collections = []
        new_item_collections = []
        for _, trees in server_collections.items():
            if dialog.is_canceled():
                return None

            for _server, tree in trees:
                if dialog.is_canceled():
                    return None

                if _index % _divisor == 0:
                    _percent += _percent_value

                dialog.update(_percent, i18n('Retrieving %s from %s for sample...') %
                              (tree.get('librarySectionTitle'), _server.get_name()))

                new_item_collections.append((_server, tree))

                _index += 1

        if new_item_collections:
            _divisor, _percent_value = self._get_progress_data(new_item_collections, 15)

            for index, (server, tree) in enumerate(new_item_collections):
                if dialog.is_canceled():
                    return None

                if index % _divisor == 0:
                    _percent += _percent_value

                dialog.update(_percent, i18n('Creating samples...'))

                item_collection = self._get_item_collection(server, tree)
                if not item_collection:
                    continue

                item_collections.append(item_collection)

        return item_collections

    def _get_section_trees(self, sections, dialog):
        trees = []

        _divisor, _percent_value = self._get_progress_data(sections, 20)
        _percent = dialog.percent

        for index, (server, section) in enumerate(sections):
            if dialog.is_canceled():
                return None

            if index % _divisor == 0:
                _percent += _percent_value

            tree = None
            if self.source == 'all':
                dialog.update(_percent,
                              i18n('Retrieving section data for %s...') % section.get_title())
                if section.content_type() == 'tvshows':
                    tree = (server, server.get_section_all(int(section.get_key()), item_type=4))
                else:
                    tree = (server, server.get_section_all(int(section.get_key())))
            elif self.source == 'on_deck':
                dialog.update(_percent,
                              i18n('Retrieving section data for %s...') % section.get_title())
                tree = (server, server.get_ondeck(section=int(section.get_key())))
            elif self.source == 'recent_added':
                dialog.update(_percent,
                              i18n('Retrieving section data for %s...') % section.get_title())
                tree = (server, server.get_recently_added(section=int(section.get_key())))
            elif self.source == 'recent_released':
                dialog.update(_percent,
                              i18n('Retrieving section data for %s...') % section.get_title())
                tree = (server, server.get_newest(section=int(section.get_key())))

            if not tree:
                continue

            trees.append(tree)

        return trees

    def _get_sample(self, item_collections):
        if self.shuffle:
            samples = self._get_shuffled_sample(item_collections)
        else:
            samples = self._get_selection_sample(item_collections)

        return [(sample[1][0], sample[1][1]) for sample in samples if sample is not None]

    @staticmethod
    def _get_distributed_by_server(trees):
        server_collections = {}

        _collections = groupby(trees, key=lambda x: x[0].get_uuid())
        for server_uuid, collection in _collections:
            server_collections[server_uuid] = list(collection)

        return server_collections

    def _get_distributed_tvshows(self, branches):
        by_show = {}

        for episode in branches:
            key = episode.get('grandparentRatingKey')
            if key not in by_show:
                by_show[key] = []
            by_show[key].append(episode)

        item_collections = [value for _, value in by_show.items()]
        zipped_collection = self._zipped_collections(item_collections)

        return list(chain.from_iterable(zipped_collection))

    @staticmethod
    def _zipped_collections(item_collections):
        zipped_collection = list(zip_longest(*item_collections))
        collection = []

        for zipped in zipped_collection:
            zipped = [_zip for _zip in zipped if _zip is not None]
            if zipped:
                collection.append(zipped)

        return collection

    def _get_distributed_collections(self, item_collections):
        collection = self._zipped_collections(item_collections)
        return chain.from_iterable(collection)

    def _get_shuffled_sample(self, item_collections):
        distributed_collection = list(self._get_distributed_collections(item_collections))

        # do some pre-shuffling, random.sample pool never felt random enough
        shuffle_times = random.randint(1, 10)
        for _ in range(shuffle_times):
            random.shuffle(distributed_collection)

        sample_size = self._limiter(self.item_count, len(distributed_collection))

        return random.sample(distributed_collection, sample_size)

    def _get_selection_sample(self, item_collections):
        distributed_collection = self._get_distributed_collections(item_collections)

        sample_items = []
        while len(sample_items) < self.item_count:
            item = next(distributed_collection, None)
            if not item:
                break
            sample_items.append(item)

        return sample_items

    @staticmethod
    def _limiter(value, upper_limit=None, lower_limit=None):
        if upper_limit is None:
            upper_limit = float('inf')
        if lower_limit is None:
            lower_limit = 0
        return upper_limit if value > upper_limit else lower_limit if value < lower_limit else value


def pyplexer_playlist(context):
    window = xbmcgui.Window(10000)
    if window.getProperty(ACTIVE_DIALOG_PROPERTY) == 'true':
        return False

    window.setProperty(ACTIVE_DIALOG_PROPERTY, 'true')
    try:
        return PlaylistConfigurator(context).run()
    except AttributeError:
        LOG.debug('Failed to load PyPlexer playlist configurator ...')
        return False
    finally:
        window.clearProperty(ACTIVE_DIALOG_PROPERTY)
