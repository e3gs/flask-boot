# -*- coding: utf-8 -*-
"""
    __init__.py
    ~~~~~~~~~~~~~~

    Project Init.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/6/11
"""

import logging
import os
from logging.handlers import SMTPHandler, RotatingFileHandler

from bson.objectid import ObjectId
from flask import Flask, g, request, flash, redirect, jsonify, url_for, render_template
from flask_babel import Babel, gettext as _
from flask_login import LoginManager, current_user
from flask_principal import Principal, identity_loaded

from app import views, helpers
from app.converters import ListConverter
from app.extensions import mail, cache, mdb
from app.models import User

DEFAULT_APP_NAME = 'app'

DEFAULT_BLUEPRINTS = (
    (views.public, "/"),
    (views.admin, "/admin")
)


def create_app(config=None, blueprints=None):
    if blueprints is None:
        blueprints = DEFAULT_BLUEPRINTS

    app = Flask(DEFAULT_APP_NAME)

    # Url converter
    app.url_map.converters['list'] = ListConverter

    # Config
    app.config.from_pyfile(config)

    # Chain
    configure_extensions(app)
    configure_login(app)
    configure_identity(app)
    configure_logging(app)
    configure_errorhandlers(app)
    configure_before_handlers(app)
    configure_template_filters(app)
    configure_context_processors(app)
    configure_i18n(app)

    # Register blueprints
    configure_blueprints(app, blueprints)

    return app


def configure_extensions(app):
    mail.init_app(app)
    cache.init_app(app)
    mdb.init_app(app)


def configure_login(app):
    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(user_id):
        # Reload the user object from the user ID stored in the session
        return User.find_one({'_id': ObjectId(user_id)})


def configure_identity(app):
    Principal(app)

    @identity_loaded.connect_via(app)
    def on_identity_loaded(sender, identity):
        # Set the identity user object
        identity.user = current_user

        # Add the UserNeed to the identity
        if hasattr(current_user, 'provides'):
            identity.provides.update(current_user.provides)


def configure_i18n(app):
    babel = Babel(app)

    @babel.localeselector
    def get_locale():
        accept_languages = app.config.get('ACCEPT_LANGUAGES', ['en', 'zh'])
        return request.accept_languages.best_match(accept_languages)


def configure_context_processors(app):
    """
    Context processors run before the template is rendered and inject new values into the template context.
    """

    @app.context_processor
    def config():
        return dict(config=app.config)


def configure_template_filters(app):
    @app.template_filter()
    def timesince(value):
        return helpers.timesince(value)


def configure_before_handlers(app):
    @app.before_request
    def authenticate():
        g.user = getattr(g.identity, 'user', None)


def configure_errorhandlers(app):
    @app.errorhandler(401)
    def unauthorized(error):
        if request.is_xhr:
            return jsonify(error=_("Login required"))
        flash(_("Please login to see this page"), "error")
        return redirect(url_for("public.login", next=request.path))

    @app.errorhandler(403)
    def forbidden(error):
        if request.is_xhr:
            return jsonify(error=_('Sorry, page not allowed'))
        return render_template("errors/403.html", error=error)

    @app.errorhandler(404)
    def page_not_found(error):
        if request.is_xhr:
            return jsonify(error=_('Sorry, page not found'))
        return render_template("errors/404.html", error=error)

    @app.errorhandler(500)
    def server_error(error):
        if request.is_xhr:
            return jsonify(error=_('Sorry, an error has occurred'))
        return render_template("errors/500.html", error=error)


def configure_blueprints(app, blueprints):
    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)


def configure_logging(app):
    mail_handler = SMTPHandler(app.config['MAIL_SERVER'], app.config['MAIL_SENDER'], app.config['MAIL_SUPPORTERS'],
                               'application error', (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD']))

    mail_handler.setLevel(logging.ERROR)
    app.logger.addHandler(mail_handler)

    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')

    debug_log = os.path.join(app.root_path, app.config['DEBUG_LOG'])
    debug_file_handler = RotatingFileHandler(debug_log, maxBytes=100000, backupCount=10)
    debug_file_handler.setLevel(logging.DEBUG)
    debug_file_handler.setFormatter(formatter)
    app.logger.addHandler(debug_file_handler)

    error_log = os.path.join(app.root_path, app.config['ERROR_LOG'])
    error_file_handler = RotatingFileHandler(error_log, maxBytes=100000, backupCount=10)
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    app.logger.addHandler(error_file_handler)
