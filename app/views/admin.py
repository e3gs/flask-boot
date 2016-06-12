# -*- coding: utf-8 -*-
"""
    admin.py
    ~~~~~~~~~~~~~~

    Admin pages.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/6/10
"""

from flask import Blueprint, render_template

admin = Blueprint("admin", __name__)


@admin.route("/crud/")
def crud():
    return render_template("admin/crud.html")
