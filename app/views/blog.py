# -*- coding: utf-8 -*-
"""
    blog
    ~~~~~~~~~~~~~~

    Blog pages/actions.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/8/16
"""

from datetime import datetime

import pymongo
from bson.objectid import ObjectId
from flask import Blueprint, request, render_template, abort, jsonify
from flask_babel import gettext as _
from flask_login import current_user, login_required

from app.decorators import user_not_rejected, user_not_evil
from app.jobs import post_view_times_counter
from app.models import Post, Tag, User
from app.mongosupport import Pagination
from app.tools import SupportMailType, send_support_email

blog = Blueprint('blog', __name__)

PAGE_COUNT = 10


@blog.route('/')
@blog.route('/index')
def index():
    """
    Index.
    """
    tid = request.args.get('t', None)
    page = int(request.args.get('p', 1))
    start = (page - 1) * PAGE_COUNT
    condition = {}
    if tid:
        condition = {'tids': ObjectId(tid)}
    count = Post.count(condition)
    cursor = Post.find(condition, skip=start, limit=PAGE_COUNT, sort=[('createTime', pymongo.DESCENDING)])
    pagination = Pagination(page, PAGE_COUNT, count)
    return render_template('blog/index.html', posts=cursor, pagination=pagination, tags=all_tags())


def all_tags():
    """
    Fetch all tags.
    """
    cursor = Tag.find({}, sort=[('weight', pymongo.DESCENDING)])
    return [t for t in cursor]


@blog.route('/post/<ObjectId:post_id>')
def post(post_id):
    """
    Post.
    """
    p = Post.find_one({'_id': post_id})
    if not p:
        abort(404)

    post_view_times_counter[post_id] += 1

    uids = set()
    for c in p.comments:
        uids.add(c.uid)
        for r in c.replys:
            uids.add(r.uid)
    user_dict = {u._id: u for u in User.find({'_id': {'$in': list(uids)}})}
    return render_template('blog/post.html', id=post_id, post=p, tags=all_tags(), user_dict=user_dict)


@blog.route('/comment/<ObjectId:post_id>', methods=('POST',))
@login_required
@user_not_rejected
@user_not_evil
def comment(post_id):
    """
    评论博文.
    """
    post = Post.find_one({'_id': post_id})
    if not post:
        return jsonify(success=False, message=_('The post does not exist!'))

    content = request.form.get('content', None)
    if not content or not content.strip():
        return jsonify(success=False, message=_('Comment content can not be blank!'))

    max = -1
    for c in post.comments:
        if max < c.id:
            max = c.id

    now = datetime.now()

    cmt = {
        'id': max + 1,
        'uid': current_user._id,
        'content': content,
        'time': now
    }

    post.comments.insert(0, cmt)
    post.save()

    send_support_email(SupportMailType.NEW_POST_COMMENT, post, content)

    return jsonify(success=True, message=_('Save comment successfully.'))


@blog.route('/reply/<ObjectId:post_id>/<int:comment_id>', methods=('POST',))
@login_required
@user_not_rejected
@user_not_evil
def reply(post_id, comment_id):
    """
    回复.
    """
    post = Post.find_one({'_id': post_id})
    if not post:
        return jsonify(success=False, message=_('The post does not exist!'))

    content = request.form.get('content', None)
    if not content or not content.strip():
        return jsonify(success=False, message=_('Reply content can not be blank!'))

    cmt = next((c for c in post.comments if c.id == comment_id), -1)
    if cmt == -1:
        return jsonify(success=False, message=_('The comment you would like to reply does not exist!'))

    now = datetime.now()

    reply = {
        'uid': current_user._id,
        'rid': ObjectId(request.form.get('rid', None)),
        'content': content,
        'time': now
    }

    cmt.replys.insert(0, reply)
    post.save()

    send_support_email(SupportMailType.NEW_POST_COMMENT, post, content)

    return jsonify(success=True, message=_('Save reply successfully.'))
