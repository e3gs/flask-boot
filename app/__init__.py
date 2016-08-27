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
from datetime import datetime
from logging.handlers import SMTPHandler, RotatingFileHandler

from bson.objectid import ObjectId
from flask import Flask, g, request, redirect, jsonify, url_for, render_template
from flask_babel import Babel, gettext as _
from flask_login import LoginManager, current_user
from flask_mobility import Mobility
from flask_principal import Principal, identity_loaded

from app import views, helpers
from app.converters import ListConverter, BSONObjectIdConverter
from app.extensions import mail, cache, mdb
from app.jobs import init_schedule
from app.models import User
from app.tools import SSLSMTPHandler

DEFAULT_APP_NAME = 'app'

DEFAULT_BLUEPRINTS = (
    (views.public, ''),
    (views.admin, '/admin'),
    (views.crud, '/crud'),
    (views.blog, '/blog')
)


def create_app(blueprints=None):
    if blueprints is None:
        blueprints = DEFAULT_BLUEPRINTS

    app = Flask(DEFAULT_APP_NAME, instance_relative_config=True)

    # Url converter
    app.url_map.converters['list'] = ListConverter
    app.url_map.converters['ObjectId'] = BSONObjectIdConverter

    # Config
    app.config.from_object('app.config')
    app.config.from_pyfile('config.py')

    # Chain
    configure_extensions(app)
    configure_mobility(app)
    configure_login(app)
    configure_identity(app)
    configure_logging(app)
    configure_errorhandlers(app)
    configure_before_handlers(app)
    configure_template_filters(app)
    configure_context_processors(app)
    configure_i18n(app)
    configure_schedulers(app)

    # Register blueprints
    configure_blueprints(app, blueprints)

    return app


def configure_extensions(app):
    mail.init_app(app)
    cache.init_app(app)
    mdb.init_app(app)


def configure_mobility(app):
    Mobility(app)


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


def configure_schedulers(app):
    init_schedule(app)


def configure_context_processors(app):
    """
    Context processors run before the template is rendered and inject new values into the template context.
    """

    @app.context_processor
    def inject_config():
        return dict(config=app.config)

    @app.context_processor
    def inject_debug():
        return dict(debug=app.debug)


def configure_template_filters(app):
    @app.template_filter()
    def timesince(value):
        return helpers.timesince(value)

    @app.template_filter()
    def date(value):
        return helpers.date(value)


def configure_before_handlers(app):
    @app.before_request
    def authenticate():
        g.user = getattr(g.identity, 'user', None)


def configure_errorhandlers(app):
    @app.errorhandler(400)
    def server_error(error):
        if request.is_xhr:
            return jsonify(success=False, message=_('Bad request!'))
        return render_template('errors/400.html', error=error)

    @app.errorhandler(401)
    def unauthorized(error):
        if request.is_xhr:
            return jsonify(success=False, message=_('Login required!'), code=1)
        return redirect(url_for('public.login', next=request.path))

    @app.errorhandler(403)
    def forbidden(error):
        if request.is_xhr:
            return jsonify(success=False, message=_('Sorry, Not allowed or forbidden!'))
        return render_template('errors/403.html', error=error)

    @app.errorhandler(404)
    def page_not_found(error):
        if request.is_xhr:
            return jsonify(success=False, message=_('Sorry, page not found!'))
        return render_template('errors/404.html', error=error)

    @app.errorhandler(500)
    def server_error(error):
        if request.is_xhr:
            return jsonify(success=False, message=_('Sorry, an error has occurred!'))
        return render_template('errors/500.html', error=error)


def configure_blueprints(app, blueprints):
    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)


def configure_logging(app):
    mail_config = [(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
                   app.config['MAIL_DEFAULT_SENDER'], app.config['ADMINS'],
                   '[Error] %s encountered errors on %s' % (app.config['DOMAIN'], datetime.now().strftime('%Y/%m/%d')),
                   (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])]
    if app.config['MAIL_USE_SSL']:
        mail_handler = SSLSMTPHandler(*mail_config)
    else:
        mail_handler = SMTPHandler(*mail_config)

    mail_handler.setLevel(logging.ERROR)
    app.logger.addHandler(mail_handler)

    formatter = logging.Formatter('%(asctime)s %(process)d-%(thread)d %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')

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

    # Flask运行在产品模式时, 只会输出ERROR, 此处使之输入INFO
    if not app.config['DEBUG']:
        app.logger.setLevel(logging.INFO)
