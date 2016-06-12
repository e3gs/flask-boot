# -*- coding: utf-8 -*-
"""
    flask_mongosupport.py
    ~~~~~~~~~~~~~~

    flask_mongosupport simplifies to use mongosupport

    :copyright: (c) 2016 by fengweimin.
    :date: 16/6/6
"""

from mongosupport import connect, get_db

# Find the stack on which we want to store the database connection.
# Starting with Flask 0.9, the _app_ctx_stack is the correct one,
# before that we need to use the _request_ctx_stack.
try:
    from flask import _app_ctx_stack as stack
except ImportError:
    from flask import _request_ctx_stack as stack


class MongoSupport(object):
    """
    This class is used to integrate `MongoSupport`_ into a Flask application.

    :param app: The Flask application will be bound to this MongoSupport instance.
                If an app is not provided at initialization time than it
                must be provided later by calling :meth:`init_app` manually.
    """

    def __init__(self, app=None):
        self.registered_models = []
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """
        This method connect your ``app`` with this extension. Flask-MongoSupport will now take care about to
        open and close the connection to your MongoDB.

        Currently, the connection is shared within the whole application, so no need to handle closing.
        """

        # Use the newstyle teardown_appcontext if it's available, otherwise fall back to the request context
        if hasattr(app, 'teardown_appcontext'):
            app.teardown_appcontext(self.teardown)
        else:
            app.teardown_request(self.teardown)

        # Connect
        conn_settings = {'db': app.config.get('MONGODB_DATABASE', 'flask'),
                         'host': app.config.get('MONGODB_HOST', '127.0.0.1'),
                         'port': app.config.get('MONGODB_PORT', 27017),
                         'username': app.config.get('MONGODB_USERNAME', None),
                         'password': app.config.get('MONGODB_PASSWORD', None)}

        connect(conn_settings.pop('db'), **conn_settings)

        # Register extension with app only to say "I'm here"
        app.extensions = getattr(app, 'extensions', {})
        app.extensions['mongosupport'] = self
        self.app = app

    def teardown(self, exception):
        pass

    def register(self, models):
        """
        Register model to flask admin, Can be also used as a decorator on documents:

        .. code-block:: python

            ms = MongoSupport(app)

            @ms.register
            class Task(Model):
                structure = {
                   'title': unicode,
                   'text': unicode,
                   'creation': datetime,
                }

        :param models: A :class:`list` of :class:`mongosupport.Model`.
        """

        # enable decorator usage
        decorator = None
        if not isinstance(models, (list, tuple, set, frozenset)):
            # we assume that the user used this as a decorator
            # using @register syntax or using db.register(SomeDoc)
            # we stock the class object in order to return it later
            decorator = models
            models = [models]

        for model in models:
            if model not in self.registered_models:
                self.registered_models.append(model)

        if decorator is None:
            return self.registered_models
        else:
            return decorator

    @property
    def db(self):
        """
        Return pymongo.database.Database
        """
        return get_db()

    def __getitem__(self, name):
        """
        Return pymongo.collection.Collection
        """
        return self.db[name]
