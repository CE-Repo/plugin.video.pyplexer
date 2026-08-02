# -*- coding: utf-8 -*-

import json
import os
import uuid
from copy import deepcopy

import xbmcvfs  # pylint: disable=import-error

from core.common import CONFIG
from core.logger import Logger

LOG = Logger('json_store')


class JSONStore:

    def __init__(self, filename):
        self.base_path = xbmcvfs.translatePath(CONFIG['addon'].getAddonInfo('profile'))
        self.filename = os.path.join(self.base_path, filename)

        self._data = None
        self.load()
        self.set_defaults()

    def set_defaults(self):
        raise NotImplementedError

    def save(self, data):
        if data == self._data:
            return True

        new_data = deepcopy(data)

        if not xbmcvfs.exists(self.base_path) and not self.make_dirs(self.base_path):
            LOG.debug('JSONStore Save |%s| failed to create directories.' % self.filename)
            return False

        LOG.debug('JSONStore Save |%s|' % self.filename)
        temporary_filename = '%s.%s.tmp' % (self.filename, uuid.uuid4().hex)
        try:
            with open(temporary_filename, 'w', encoding='utf-8') as jsonfile:
                json.dump(new_data, jsonfile, indent=4, sort_keys=True)
                jsonfile.flush()
            os.replace(temporary_filename, self.filename)
        except (OSError, TypeError, ValueError) as error:
            LOG.error('JSONStore Save |%s| failed: %s' % (self.filename, error))
            if temporary_filename and os.path.exists(temporary_filename):
                try:
                    os.remove(temporary_filename)
                except OSError:
                    pass
            return False

        self._data = new_data
        return True

    def load(self):
        if not xbmcvfs.exists(self.filename):
            self._data = {}
            return

        try:
            with open(self.filename, 'r', encoding='utf-8') as jsonfile:
                self._data = json.load(jsonfile)
            LOG.debug('JSONStore Load |%s|' % self.filename)
        except (OSError, ValueError) as error:
            # a corrupt or unreadable store must not stop the add-on from
            # starting, fall back to an empty one
            LOG.error('JSONStore Load |%s| failed: %s' % (self.filename, error))
            self._data = {}

    def get_data(self):
        return deepcopy(self._data)

    @staticmethod
    def make_dirs(path):
        if not path.endswith('/'):
            path = ''.join([path, '/'])
        path = xbmcvfs.translatePath(path)

        if xbmcvfs.exists(path):
            return True

        try:
            xbmcvfs.mkdirs(path)
        except Exception as error:  # pylint: disable=broad-except
            LOG.debug('JSONStore xbmcvfs.mkdirs |%s| failed: %s' % (path, error))

        if not xbmcvfs.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as error:
                LOG.debug('JSONStore os.makedirs |%s| failed: %s' % (path, error))

        return xbmcvfs.exists(path)
