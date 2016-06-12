# -*- coding: utf-8 -*-
"""
    __init__.py
    ~~~~~~~~~~~~~~

    Model user.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/6/11
"""

from datetime import datetime

from flask_login import UserMixin
from flask_principal import RoleNeed, UserNeed
from werkzeug.utils import cached_property

from app.extensions import mdb
from app.mongosupport import Model


@mdb.register
class User(Model, UserMixin):
    # User roles
    MEMBER = 1
    ADMIN = 9

    __collection__ = 'users'
    structure = {
        'name': unicode,
        'email': unicode,
        'password': unicode,
        'head': unicode,
        'roles': [int],
        'createTime': datetime,
        'updateTime': datetime
    }
    required_fields = ['email', 'password', 'name', 'createTime']
    default_values = {'createTime': datetime.now(), 'roles': [MEMBER]}
    indexes = [{'fields': ['email'], 'unique': True}]

    @cached_property
    def provides(self):
        """
        Provide user's identity
        """
        needs = [RoleNeed('authenticated'),
                 UserNeed(self._id)]

        if self.is_admin:
            needs.append(RoleNeed('admin'))

        return needs

    @cached_property
    def is_admin(self):
        return self.ADMIN in self.roles

    # UserMixin of flask-login
    def get_id(self):
        return str(self._id)
