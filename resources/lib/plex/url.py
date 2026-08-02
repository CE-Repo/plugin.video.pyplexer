# -*- coding: utf-8 -*-

"""Helpers for formatting IPv4, IPv6 and hostname based Plex addresses."""

from urllib.parse import urlparse


def normalize_host(host):
    host = str(host or '').strip()
    if host.startswith('[') and host.endswith(']'):
        return host[1:-1]
    return host


def format_host(host):
    host = normalize_host(host)
    return '[%s]' % host if ':' in host else host


def format_netloc(host, port=None):
    host = format_host(host)
    if not host:
        return ''
    return '%s:%s' % (host, port) if port not in (None, '') else host


def split_netloc(netloc, default_port=None):
    """Return an unbracketed host and port from a URL network location."""
    netloc = str(netloc or '').rsplit('@', 1)[-1].strip()
    if not netloc:
        return '', default_port

    # A bare IPv6 literal has no unambiguous port. Treat the whole value as
    # the host; callers that have a port pass it separately to format_netloc.
    if netloc.count(':') > 1 and not netloc.startswith('['):
        return normalize_host(netloc), default_port

    parsed = urlparse('//%s' % netloc)
    try:
        port = parsed.port
    except ValueError:
        port = None
    port = port or default_port
    return normalize_host(parsed.hostname or netloc), str(port) if port is not None else None


def ensure_netloc(value, default_port=None):
    host, port = split_netloc(value, default_port)
    return format_netloc(host, port)
