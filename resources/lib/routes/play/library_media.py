# -*- coding: utf-8 -*-

from core.utils import get_transcode_profile
from playback.engine import play_library_media
from playback.engine import play_media_id_from_uuid
from plex.network import Plex
from storage.data_cache import DATA_CACHE


def run(context, data):
    context.plex_network = Plex(context.settings, load=True)

    data.setdefault('transcode', False)
    data.setdefault('transcode_profile', None)

    if data['transcode'] and data['transcode_profile'] is None:
        data['transcode_profile'] = get_transcode_profile(context)
    if data['transcode_profile'] is None:
        data['transcode_profile'] = 0

    if not data.get('url'):
        if data.get('server_uuid') and data.get('media_id'):
            play_media_id_from_uuid(context, data)
            DATA_CACHE.delete_cache(True)
        return

    play_library_media(context, data)
    DATA_CACHE.delete_cache(True)
