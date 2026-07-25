# -*- coding: utf-8 -*-

from core.settings import AddonSettings
from storage.http_cache import CacheControl

DATA_CACHE = CacheControl('data', AddonSettings().data_cache())
