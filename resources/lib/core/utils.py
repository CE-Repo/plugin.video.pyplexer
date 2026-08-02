# -*- coding: utf-8 -*-

import json
import os
import pickle
import time
from base64 import b64encode
from binascii import hexlify
from urllib.parse import urlencode

import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n

LOG = Logger()

#: Items whose streams are fetched in one go; a whole library page is left
#: alone, nobody compares five hundred titles at once.
MAX_STREAM_LOOKUP = 30

#: Everything the stream lookup does not need, kept out of the answer.
SKIPPED_ELEMENTS = ('Genre', 'Country', 'Role', 'Writer', 'Director', 'Producer',
                    'Collection', 'Rating', 'Review', 'Chapter', 'Similar',
                    'Related', 'Extras', 'Preferences', 'Guid',
                    'UltraBlurColors', 'Marker')


def get_xml(context, url, tree=None):
    if tree is None:
        tree = context.plex_network.get_processed_xml(url)

    if tree.get('message'):
        xbmcgui.Dialog().ok(tree.get('header', i18n('Message')), tree.get('message', ''))
        return None

    return tree


def attach_media_streams(server, elements):
    """Fetch the streams of the given items and graft them onto their Media.

    Plex answers a listing or a search with the attributes of a Media element
    only - the streams below it live on the metadata of the item.  Without them
    there is no Dolby Vision profile, no audio language and no subtitle list.
    Several rating keys can be asked for at once, so a whole page costs one
    request, and everything but the media data is left out of the answer.

    The elements are changed in place; anything that goes wrong leaves them as
    they were.
    """
    elements = [element for element in elements
                if element.get('ratingKey') and element.find('Media') is not None]

    if not elements or len(elements) > MAX_STREAM_LOOKUP:
        return False

    if all(element.find('.//Stream') is not None for element in elements):
        return False  # the response already carries them

    query = urlencode({
        'excludeElements': ','.join(SKIPPED_ELEMENTS),
        'excludeFields': 'summary,tagline',
    })

    try:
        tree = server.processed_xml('/library/metadata/%s?%s' %
                                    (','.join([element.get('ratingKey')
                                               for element in elements]), query))
    except Exception as error:  # pylint: disable=broad-except
        LOG.debug('Stream lookup failed on %s: %s' % (server.get_name(), error))
        return False

    if tree is None:
        return False

    detailed = {}
    for video in tree.iter('Video'):
        rating_key = video.get('ratingKey')
        if rating_key:
            detailed[str(rating_key)] = video

    grafted = 0
    for element in elements:
        video = detailed.get(str(element.get('ratingKey')))
        if video is None or video.find('Media') is None:
            continue

        for media in element.findall('Media'):
            element.remove(media)
        for media in video.findall('Media'):
            element.append(media)

        # the same answer holds the artwork the listing left out, the clear
        # logo among it
        if element.find('Image') is None:
            for image in video.findall('Image'):
                element.append(image)

        grafted += 1

    LOG.debug('Streams attached to %s of %s item(s) on %s' %
              (grafted, len(elements), server.get_name()))

    return grafted > 0


def get_master_server(context, all_servers=False):
    possible_servers = []
    append_server = possible_servers.append
    current_master = context.settings.master_server()
    for server_data in context.plex_network.get_server_list():
        LOG.debug(str(server_data))
        if server_data.get_master() == 1:
            append_server(server_data)
    LOG.debug('Possible master servers are: %s' % possible_servers)

    if all_servers:
        return possible_servers

    if len(possible_servers) > 1:
        preferred = 'local'
        for server_data in possible_servers:
            if server_data.get_name() == current_master:
                LOG.debug('Returning current master')
                return server_data
            if preferred == 'any':
                LOG.debug('Returning \'any\'')
                return server_data
            if server_data.get_discovery() == preferred:
                LOG.debug('Returning local')
                return server_data

    if len(possible_servers) == 0:
        return None

    return possible_servers[0]


PROFILE_COUNT = 3


def get_transcode_profile(context):
    """
    Ask the user which of the enabled transcode profiles to use and return its
    profile index (the index ``AddonSettings.transcode_profile()`` expects).
    """
    profile_labels = []
    profile_indexes = []

    for idx in range(PROFILE_COUNT):
        profile = context.settings.transcode_profile(idx)
        if not profile.get('enabled'):
            continue

        quality = profile.get('quality') or ','
        resolution, _, bitrate = quality.partition(',')
        profile_labels.append('[%s] %s@%s (%s/%s)' %
                              (idx + 1, resolution.strip(), bitrate.strip(),
                               profile.get('subtitle_size'), profile.get('audio_boost')))
        profile_indexes.append(idx)

    if len(profile_indexes) <= 1:
        # profile 0 is always enabled, so there is nothing to choose from
        return profile_indexes[0] if profile_indexes else 0

    result = xbmcgui.Dialog().select(i18n('Transcode Profiles'), profile_labels)

    if result == -1:
        return 0

    # the dialog index is a position in the enabled subset, not a profile index
    return profile_indexes[result]


def write_pickled(filename, data):
    try:
        os.makedirs(CONFIG['temp_path'], exist_ok=True)
    except OSError as error:
        LOG.error('Unable to create %s: %s' % (CONFIG['temp_path'], error))
        return False

    filename = os.path.join(CONFIG['temp_path'], filename)
    try:
        with open(filename, 'wb') as open_file:
            open_file.write(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL))
    except (OSError, pickle.PicklingError) as error:
        LOG.error('Unable to write %s: %s' % (filename, error))
        return False

    return True


def read_pickled(filename, delete_after=True):
    filename = os.path.join(CONFIG['temp_path'], filename)
    if not os.path.exists(filename):
        return None

    try:
        with open(filename, 'rb') as open_file:
            pickled_data = open_file.read()
    except OSError as error:
        LOG.error('Unable to read %s: %s' % (filename, error))
        return None

    if delete_after:
        try:
            os.remove(filename)
        except OSError as error:
            LOG.debug('Unable to remove %s: %s' % (filename, error))

    try:
        return pickle.loads(pickled_data)
    except Exception as error:  # pylint: disable=broad-except
        # unpickling a truncated or stale file can raise almost anything
        LOG.error('Unable to unpickle %s: %s' % (filename, error))
        return None


def notify_all(encoding, method, data):
    encoded = json.dumps(data).encode('utf-8')

    if encoding == 'base64':
        data = b64encode(encoded).decode('ascii')
    elif encoding == 'hex':
        data = hexlify(encoded).decode('ascii')
    else:
        # the receiver expects a string, not the raw object
        data = encoded.decode('utf-8')

    jsonrpc_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "JSONRPC.NotifyAll",
        "params": {
            "sender": "%s.SIGNAL" % CONFIG['id'],
            "message": method,
            "data": [data],
        }
    }

    xbmc.executeJSONRPC(json.dumps(jsonrpc_request))


def jsonrpc_play(url):
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "player.open",
        "params": {
            "item": {
                "file": url
            }
        }
    }

    xbmc.executeJSONRPC(json.dumps(jsonrpc_request))


def wait_for_busy_dialog():
    """
    Wait for busy dialogs to close, starting playback while the busy dialog is active
    could crash Kodi 18 / 19 (pre-alpha)

    Github issues:
        https://github.com/xbmc/xbmc/issues/16756
        https://github.com/xbmc/xbmc/pull/16450  # possible solution

    TODO: remove this function when the above issue is resolved
    """
    monitor = xbmc.Monitor()
    start_time = time.time()
    xbmc.sleep(500)

    def _abort():
        return monitor.abortRequested()

    def _busy():
        return xbmcgui.getCurrentWindowDialogId() in [10138, 10160]

    def _wait():
        LOG.debug('Waiting for busy dialogs to close ...')
        while not _abort() and _busy():
            if monitor.waitForAbort(1):
                break

    while not _abort():
        if _busy():
            _wait()

        if monitor.waitForAbort(1):
            break

        if not _busy():
            break

    LOG.debug('Waited %.2f for busy dialogs to close.' % (time.time() - start_time))
    return not _abort() and not _busy()


def get_file_type(filename):
    if not filename:
        return None

    if filename[0:2] == '\\\\':
        LOG.debug('Detected UNC source file')
        return 'UNC'
    if filename[0:1] in ['/', '\\']:
        LOG.debug('Detected unix source file')
        return 'NIX'
    # the second half used to compare a one character slice against ':/',
    # so drive letters with forward slashes were never detected
    if filename[1:3] in (':\\', ':/'):
        LOG.debug('Detected windows source file')
        return 'WIN'

    LOG.debug('Unknown file type source: %s' % filename)
    return None
