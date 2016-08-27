# -*- coding: utf-8 -*-
"""
    notifier
    ~~~~~~~~~~~~~~

    Notifier, which is used to send email/sms notifications.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/8/14
"""

from datetime import datetime

from flask import current_app
from flask_mail import Message

from app.decorators import async
from app.extensions import mail


def send_support_email(type, body, **kwargs):
    """
    For email setting, please refer to `Flask-Mail <https://pythonhosted.org/Flask-Mail/>`.
    """
    # flask.current_app is a proxy.
    # http://flask.pocoo.org/docs/0.11/reqcontext/#notes-on-proxies
    app = kwargs.get('app', None)
    if not app:
        app = current_app._get_current_object()

    subject = '[Info] %s: %s on %s' % (app.config['DOMAIN'], type, datetime.now().strftime('%Y/%m/%d'))
    recipients = app.config['ADMINS']
    app.logger.info('Try to send support email %s to %s' % (subject, recipients))
    send_async_email(app, subject, recipients, body)


@async
def send_async_email(app, subject, recipients, body):
    with app.app_context():
        msg = Message(subject, recipients, body)
        mail.send(msg)
