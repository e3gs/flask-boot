# -*- coding: utf-8 -*-
"""
    extension.py
    ~~~~~~~~~~~~~~

    Extension reference.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/5/9
"""

from flask_cache import Cache
from flask_mail import Mail

from app.mongosupport import MongoSupport

__all__ = ['mail', 'cache', 'mdb']

mail = Mail()
cache = Cache()
mdb = MongoSupport()
