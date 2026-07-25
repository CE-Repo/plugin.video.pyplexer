# -*- coding: utf-8 -*-

import re
import socket
from contextlib import closing

from core.logger import Logger

LOG = Logger()

# 9 (discard) is the conventional Wake On LAN port, 7 (echo) is also widely
# used; the packet is broadcast to both so either configuration works.
WOL_PORTS = (9, 7)
SEPARATORS = re.compile(r'[\s:.\-]')


def wake_servers(context):
    if not context.settings.wake_on_lan():
        return

    LOG.debug('Wake On LAN: true')
    for mac_address in context.settings.get_wakeservers():
        if not mac_address:
            continue

        try:
            LOG.debug('Waking server with MAC: %s' % mac_address)
            wake_on_lan(mac_address)
        except ValueError as error:
            LOG.debug('Incorrect MAC address format for server %s: %s' % (mac_address, error))
        except OSError as error:
            LOG.debug('Wake on lan error for server %s: %s' % (mac_address, error))


def magic_packet(mac_address):
    """
    Build the Wake On LAN magic packet for ``mac_address``.

    Six ``0xFF`` bytes followed by the six byte hardware address repeated
    sixteen times, as described by AMD's Magic Packet Technology paper.
    """
    address = SEPARATORS.sub('', mac_address.strip())

    if len(address) != 12:
        raise ValueError('Incorrect MAC address format')

    try:
        hardware_address = bytes.fromhex(address)
    except ValueError as error:
        raise ValueError('Incorrect MAC address format') from error

    return b'\xff' * 6 + hardware_address * 16


def wake_on_lan(mac_address):
    """ Switches on remote computers using WOL. """
    packet = magic_packet(mac_address)

    with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as open_socket:
        open_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in WOL_PORTS:
            open_socket.sendto(packet, ('<broadcast>', port))
