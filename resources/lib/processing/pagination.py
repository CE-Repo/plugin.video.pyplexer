# -*- coding: utf-8 -*-

"""Server-side pagination for Plex directory listings."""

import math
import xml.etree.ElementTree as ETree
from urllib.parse import parse_qsl
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import xbmcgui  # pylint: disable=import-error

from core.constants import CONFIG
from core.strings import i18n_or

PAGE_SIZE = 100

_INTERNAL_PARAMETERS = ('command', 'path_mode', 'page')


def is_paged_listing(url):
    """Return whether ``url`` can represent a remote Plex container."""
    if not url:
        return False
    try:
        parts = urlsplit(str(url))
        if parts.scheme.lower() not in ('http', 'https'):
            return False
        for name, value in parse_qsl(parts.query, keep_blank_values=True):
            if name.lower() != 'x-plex-container-size':
                continue
            try:
                return int(value) >= PAGE_SIZE
            except (TypeError, ValueError):
                return True
        return True
    except (TypeError, ValueError):
        return False


def page_number(context):
    """Return the requested one-based page, safely defaulting to page one."""
    try:
        page = int(context.params.get('page', 1))
    except (AttributeError, TypeError, ValueError):
        page = 1
    return max(1, page)


def paged_listing_url(context, url):
    """Limit one remote Plex container request to the requested page."""
    if not is_paged_listing(url):
        return url

    parts = urlsplit(str(url))
    query = [(name, value) for name, value in
             parse_qsl(parts.query, keep_blank_values=True)
             if name.lower() not in
             ('x-plex-container-start', 'x-plex-container-size')]
    query.extend((
        ('X-Plex-Container-Start', (page_number(context) - 1) * PAGE_SIZE),
        ('X-Plex-Container-Size', PAGE_SIZE),
    ))
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_item(context, label, target_page):
    params = {
        name: value for name, value in context.params.items()
        if name not in _INTERNAL_PARAMETERS and value is not None
    }
    params['page'] = str(target_page)

    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    list_item.setArt({
        'icon': 'DefaultFolder.png',
        'thumb': 'DefaultFolder.png',
    })
    list_item.setProperty('IsPlayable', 'false')
    query = urlencode(params, quote_via=quote)
    return 'plugin://%s/?%s' % (CONFIG['id'], query), list_item, True


def add_page_navigation(context, url, tree, items):
    """Add a next-page folder; Kodi itself provides backwards navigation."""
    if tree is None or not is_paged_listing(url):
        return items

    current_page = page_number(context)
    returned = _integer(tree.get('size'), len(tree))
    total_value = tree.get('totalSize')
    total_known = total_value is not None
    total = _integer(total_value, returned)
    total = max(total, ((current_page - 1) * PAGE_SIZE) + returned)
    total_pages = max(current_page, int(math.ceil(float(total) / PAGE_SIZE)))

    has_next = current_page < total_pages
    # Older Plex versions may omit totalSize. A full page then signals that
    # another request is worth offering; an empty/partial page is the end.
    if not total_known:
        has_next = returned >= PAGE_SIZE

    next_item = None
    if has_next:
        label = u'%s (%s/%s) \u2192' % (
            i18n_or('Next page', 'Next page'),
            current_page + 1, max(total_pages, current_page + 1))
        next_item = _page_item(context, label, current_page + 1)

    if next_item:
        items.append(next_item)
    return items


def paginate_local_items(context, items):
    """Slice a list assembled locally and append its next-page folder."""
    items = list(items)
    total = len(items)
    start = (page_number(context) - 1) * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    container = ETree.Element('MediaContainer', {
        'size': str(len(page_items)),
        'totalSize': str(total),
    })
    add_page_navigation(context, 'http://pyplexer/local', container,
                        page_items)
    return page_items
