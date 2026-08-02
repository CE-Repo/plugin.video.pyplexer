# -*- coding: utf-8 -*-

"""Shared HTTP transport for Plex and plex.tv requests."""

import threading

import requests
from requests.adapters import HTTPAdapter


# Metadata calls should fail fast enough that Kodi's UI remains responsive.
DIRECT_TIMEOUT = (2, 5)
CONNECTION_TEST_TIMEOUT = (2, 10)
ACCOUNT_TIMEOUT = (3, 20)
SERVER_TIMEOUT = (3, 30)
SIGN_IN_TIMEOUT = (3, 30)

_LOCAL = threading.local()


def _session():
    """Return one pooled Session per thread.

    Server discovery probes run concurrently. A thread-local session retains
    connection pooling without sharing mutable Session state between probes.
    """
    session = getattr(_LOCAL, 'session', None)
    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        _LOCAL.session = session
    return session


def request(method, url, timeout=SERVER_TIMEOUT, **kwargs):
    """Send an HTTP request with pooled connections and a bounded timeout."""
    method = str(method).lower()
    if method not in ('delete', 'get', 'head', 'patch', 'post', 'put'):
        raise ValueError('Unsupported HTTP method: %s' % method)
    return _session().request(method, url, timeout=timeout, **kwargs)
