# -*- coding: utf-8 -*-
"""
    crud
    ~~~~~~~~~~~~~~

    CRUD.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/7/24
"""

from collections import OrderedDict

from bson.objectid import ObjectId
from flask import Blueprint, render_template, abort, current_app, request, jsonify
from pymongo.errors import DuplicateKeyError

from app.extensions import mdb
from app.mongosupport import Pagination, populate_model, MongoSupportError
from app.permissions import admin_permission

crud = Blueprint('crud', __name__)

PAGE_COUNT = 30


@crud.route('/index')
@crud.route('/index/<string:model_name>')
@admin_permission.require(403)
def index(model_name=None):
    """
    Index page.
    """
    registered_models = mdb.registered_models
    if model_name:
        model = next((m for m in registered_models if m.__name__.lower() == model_name.lower()), None)
    elif registered_models:
        model = registered_models[0]
    if not model:
        abort(404)

    model_name = model.__name__.lower()
    # 获取指定model的索引
    index_dict = OrderedDict({'_id': ObjectId})
    for i in model.indexes:
        value = i['fields']
        if isinstance(value, basestring):
            index_dict[value] = model._valid_paths[value]
        elif isinstance(value, list):
            for val in value:
                if isinstance(val, tuple):
                    field, direction = val
                    index_dict[field] = model._valid_paths[field]
                else:
                    index_dict[val] = model._valid_paths[val]

    # 根据条件进行查询
    # TODO: 排序
    page = int(request.args.get('_p', 1))
    # 调用populate_model将查询条件转化为数据对象, 会自动转换查询条件的数据类型
    search_record = populate_model(request.args, model, False)
    # 将数据对象中非空的值提取出来, 构造成一个mongoDB查询的条件
    condition = {f: v for f, v in search_record.iteritems() if v}
    # 用于计算总页数
    count = model.count(condition)
    current_app.logger.debug('There are %s %ss for condition %s' % (count, model_name, condition))
    start = (page - 1) * PAGE_COUNT
    # 返回结果只显示索引中的字段
    projection = dict.fromkeys(index_dict.keys(), True)
    records = model.find(condition, projection, start, PAGE_COUNT)
    pagination = Pagination(page, PAGE_COUNT, count)

    # current_app.logger.debug('Indexed fields for %s are %s' % (model_name, index_dict))
    return render_template('/crud/index.html',
                           models=registered_models,
                           model=model,
                           search_record=search_record,
                           index_dict=index_dict,
                           records=records,
                           pagination=pagination)


@crud.route('/new/<string:model_name>')
@crud.route('/change/<string:model_name>/<ObjectId:record_id>')
@admin_permission.require(403)
def form(model_name, record_id=None):
    """
    Form page which is used to new/change a record.
    """
    registered_models = mdb.registered_models
    model = next((m for m in registered_models if m.__name__.lower() == model_name.lower()), None)

    if record_id:
        record = model.find_one({'_id': record_id})
        if not record:
            abort(404)
    else:
        record = model()

    return render_template('/crud/form.html',
                           model=model,
                           record=record)


@crud.route('/create/<string:model_name>', methods=('POST',))
@crud.route('/save/<string:model_name>/<ObjectId:record_id>', methods=('POST',))
@admin_permission.require(403)
def save(model_name, record_id=None):
    """
    Create a new record or save an existing record.
    """
    registered_models = mdb.registered_models
    model = next((m for m in registered_models if m.__name__.lower() == model_name.lower()), None)

    try:
        record = populate_model(request.form, model, False);
        if record_id:
            record._id = record_id
            record.save()
        else:
            record._id = ObjectId()
            record.save(True)
    except (MongoSupportError, DuplicateKeyError) as err:
        return jsonify(success=False, message='Save failed! (%s)' % unicode(err.message))
    except:
        current_app.logger.exception('Failed when saving %s' % model_name)
        return jsonify(success=False, message='Save failed!')

    return jsonify(success=True, message='Save successfully. (%s)' % unicode(record._id))


@crud.route('/delete/<string:model_name>/<ObjectId:record_id>', methods=('POST',))
def delete(model_name, record_id):
    """
    Delete record.
    """
    registered_models = mdb.registered_models
    model = next((m for m in registered_models if m.__name__.lower() == model_name.lower()), None)

    record = model.find_one({'_id': record_id})
    if not record:
        abort(404)
    record.delete()

    return jsonify(success=True, message='Delete successfully. (%s)' % unicode(record_id))
