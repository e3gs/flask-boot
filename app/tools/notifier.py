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


class SupportMailType(object):
    """
    Support email types predefined.
    """
    NEW_USER = 'NEW_USER'
    NEW_POST_COMMENT = 'NEW_POST_COMMENT'


def send_support_email(type, *args, **kwargs):
    """
    For email setting, please refer to `Flask-Mail <https://pythonhosted.org/Flask-Mail/>`.
    """
    # flask.current_app is a proxy.
    # http://flask.pocoo.org/docs/0.11/reqcontext/#notes-on-proxies
    app = current_app._get_current_object()
    subject = '[Info] %s:: %s on %s' % (app.config['DOMAIN'], type, datetime.now().strftime('%Y/%m/%d'))
    recipients = app.config['ADMINS']

    if type == SupportMailType.NEW_USER:
        user = args[0]
        body = u'User email is %s and name is %s' % (user.email, user.name)
    elif type == SupportMailType.NEW_POST_COMMENT:
        post = args[0]
        comment = args[1]
        body = u'New comment on post is %s/%s: %s' % (post._id, post.title, comment)

    if body:
        app.logger.info('Try to send support email %s to %s' % (subject, recipients))
        msg = Message(subject, recipients, body)
        send_async_email(app, msg)


@async
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)
