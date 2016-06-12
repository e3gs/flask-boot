# -*- coding: utf-8 -*-
"""
    public.py
    ~~~~~~~~~~~~~~

    Public pages.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/5/12
"""

from flask import Blueprint, render_template

public = Blueprint("public", __name__)


@public.route("/")
def index():
    """
    Index page.
    """
    return render_template("public/index.html")
