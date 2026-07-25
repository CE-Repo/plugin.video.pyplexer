# -*- coding: utf-8 -*-

import sys

import xbmc  # pylint: disable=import-error


def strip_transcode(url):
    url = url.replace('&transcode=0', '')
    url = url.replace('&transcode=1', '')
    return url


if __name__ == '__main__':
    # sys.listitem is injected by Kodi when running as a context menu item
    info_tag = sys.listitem.getVideoInfoTag()  # pylint: disable=no-member

    try:
        plugin_url = info_tag.getFilenameAndPath()
    except AttributeError:
        plugin_url = xbmc.getInfoLabel('ListItem.FileNameAndPath')

    plugin_url = strip_transcode(plugin_url)
    plugin_url += '&transcode=1'
    xbmc.executebuiltin('PlayMedia(%s)' % plugin_url)
