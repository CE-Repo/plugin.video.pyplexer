# -*- coding: utf-8 -*-

from core.constants import CONFIG
from core.logger import Logger
from plex.discovery import PlexGDM

LOG = Logger()


# Start GDM for server/client discovery
def get_client(settings):
    client = PlexGDM()
    details = settings.companion_receiver()
    data = {
        'uuid': details['uuid'],
        'name': details['name'],
        'port': details['port'],
        'product': {
            'name': CONFIG['name'],
            'version': CONFIG['version'],
        }
    }
    client.client_details(data)

    LOG.debug('Registration string is: %s' % client.get_client_details())
    return client
