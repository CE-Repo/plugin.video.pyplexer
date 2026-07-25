# -*- coding: utf-8 -*-
"""
    Class: CacheControl

    Implementation of file based caching for python objects.
    Utilises pickle to store object data as file within the KODI virtual file system.
"""

import hashlib
import os
import pickle
import shutil
import time

import xbmcvfs  # pylint: disable=import-error

from core.constants import CONFIG
from core.logger import Logger

LOG = Logger('cachecontrol')


class CacheControl:
    # ADDON_DATA_FOLDER is hardcoded and is used for path protection
    # Cache will only enable/delete if the path is in the add-on's addon_data folder
    ADDON_DATA_FOLDER = 'special://profile/addon_data/plugin.video.pyplexer/'

    def __init__(self, cache_location, enabled=True):
        if not CONFIG['cache_path'].startswith(self.ADDON_DATA_FOLDER):
            LOG.debug('CACHE: Cache is disabled, the cache path is'
                      ' not in the addon_data folder')
            enabled = False

        self.cache_location = None
        self.enabled = False

        if not enabled:
            LOG.debug('Cache is disabled')
            return

        location = xbmcvfs.translatePath(os.path.join(CONFIG['cache_path'], cache_location))

        delimiter = '/' if '/' in location else '\\'
        if not location.endswith(delimiter):
            location += delimiter

        if not xbmcvfs.exists(location):
            LOG.debug('CACHE [%s]: Location does not exist.  Creating' % location)
            if not xbmcvfs.mkdirs(location):
                LOG.debug('CACHE [%s]: Location cannot be created' % location)
                return

        self.cache_location = location
        self.enabled = True
        LOG.debug('Running with cache location: %s' % self.cache_location)

    def read_cache(self, cache_name):
        if self.cache_location is None:
            return False, None

        LOG.debug('CACHE [%s]: attempting to read' % cache_name)
        try:
            cache = xbmcvfs.File(self.cache_location + cache_name)
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('CACHE [%s]: open error [%s]' % (cache_name, error))
            return False, None

        try:
            cache_data = cache.readBytes()
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('CACHE [%s]: read error [%s]' % (cache_name, error))
            cache_data = None
        finally:
            cache.close()

        if not cache_data:
            LOG.debug('CACHE [%s]: empty' % cache_name)
            return False, None

        if isinstance(cache_data, str):
            cache_data = cache_data.encode('utf-8')

        LOG.debug('CACHE [%s]: read' % cache_name)
        try:
            return True, pickle.loads(cache_data)
        except Exception as error:  # pylint: disable=broad-except
            # a truncated or otherwise corrupt cache file must never be fatal;
            # unpickling can raise just about anything
            LOG.debug('CACHE [%s]: unpickle error [%s]' % (cache_name, error))
            return False, None

    def write_cache(self, cache_name, obj):

        if self.cache_location is None:
            return False

        LOG.debug('CACHE [%s]: Writing file' % cache_name)
        try:
            cache = xbmcvfs.File(self.cache_location + cache_name, 'w')
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('CACHE [%s]: open error [%s]' % (cache_name, error))
            return False

        try:
            cache.write(bytearray(pickle.dumps(obj)))
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('CACHE [%s]: Writing error [%s]' %
                      (self.cache_location + cache_name, error))
            return False
        finally:
            cache.close()

        return True

    def is_valid(self, cache_name, ttl=3600):
        if self.cache_location is None:
            return None

        if xbmcvfs.exists(self.cache_location + cache_name):
            LOG.debug('CACHE [%s]: exists, ttl: |%s|' % (cache_name, str(ttl)))
            now = int(round(time.time(), 0))
            modified = int(xbmcvfs.Stat(self.cache_location + cache_name).st_mtime())
            LOG.debug('CACHE [%s]: mod[%s] now[%s] diff[%s]' %
                      (cache_name, modified, now, now - modified))

            if (modified < 0) or (now - modified) > ttl:
                return False

            return True

        LOG.debug('CACHE [%s]: does not exist' % cache_name)
        return None

    def check_cache(self, cache_name, ttl=3600):
        if self.cache_location is None:
            return False, None

        cache_valid = self.is_valid(cache_name, ttl)

        if cache_valid is False:
            LOG.debug('CACHE [%s]: too old, delete' % cache_name)
            if xbmcvfs.delete(self.cache_location + cache_name):
                LOG.debug('CACHE [%s]: deleted' % cache_name)
            else:
                LOG.debug('CACHE [%s]: not deleted' % cache_name)

        elif cache_valid:
            LOG.debug('CACHE [%s]: current' % cache_name)
            return self.read_cache(cache_name)

        return False, None

    def delete_cache(self, force=False):
        if not CONFIG['cache_path'].startswith(self.ADDON_DATA_FOLDER):
            LOG.debug('CACHE: Cache not deleted, the cache path is'
                      ' not in the addon_data folder')
            return

        if self.cache_location is None:
            LOG.debug('CACHE: Cache not deleted, the cache is disabled')
            return

        start_time = time.time()

        persistent_cache_suffix = '.pcache'

        if force:
            folder_deleted = self.delete_cache_folder()
            if folder_deleted:
                LOG.debug('Deleted cache in |%.3fs|' % (time.time() - start_time))
                return

        dirs, file_list = xbmcvfs.listdir(self.cache_location)

        LOG.debug('List of file: [%s]' % file_list)
        LOG.debug('List of dirs: [%s]' % dirs)

        cache_files = []
        append = cache_files.append
        path_join = os.path.join
        has_persistent = False

        for cache_file in file_list:
            if cache_file.endswith(persistent_cache_suffix):
                has_persistent = True

            if not force and cache_file.endswith(persistent_cache_suffix):
                continue

            append(path_join(self.cache_location, cache_file))

        folder_deleted = False
        if not has_persistent:
            folder_deleted = self.delete_cache_folder()

        delete = xbmcvfs.delete
        if not folder_deleted:
            for cache_file in cache_files:
                if delete(cache_file):
                    LOG.debug('SUCCESSFUL: removed %s' % cache_file)
                else:
                    LOG.debug('UNSUCCESSFUL: did not remove %s' % cache_file)

        LOG.debug('Deleted cache in |%.3fs|' % (time.time() - start_time))

    def delete_cache_folder(self):
        if self.cache_location is None:
            return False

        if xbmcvfs.exists(self.cache_location):
            shutil.rmtree(self.cache_location, ignore_errors=True)

        if not xbmcvfs.exists(self.cache_location):
            LOG.debug('SUCCESSFUL: removed %s' % self.cache_location)
            xbmcvfs.mkdirs(self.cache_location)
            return True

        LOG.debug('UNSUCCESSFUL: did not remove %s' % self.cache_location)
        return False

    @staticmethod
    def sha512_cache_name(name, unique_id, data):
        if not isinstance(name, bytes):
            name = name.encode('utf-8')
        if not isinstance(unique_id, bytes):
            unique_id = unique_id.encode('utf-8')
        if not isinstance(data, bytes):
            data = data.encode('utf-8')

        name_hash = hashlib.sha512()
        name_hash.update(name + unique_id + data)
        cache_name = name_hash.hexdigest()

        if isinstance(cache_name, bytes):
            cache_name = cache_name.decode('utf-8')

        return cache_name + '.cache'
