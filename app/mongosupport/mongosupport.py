# -*- coding: utf-8 -*-
"""
    mongosupport.py
    ~~~~~~~~~~~~~~

    定义的对象只要继承MongoSupport即可获取读写MongoDB的能力

    :copyright: (c) 2016 by fengweimin.
    :date: 16/5/25
"""

from collections import MutableSequence, MutableMapping
from copy import deepcopy
from datetime import datetime

import pymongo
from bson.binary import Binary
from bson.objectid import ObjectId
from pymongo import MongoClient, ReadPreference, uri_parser, WriteConcern
from pymongo.cursor import Cursor as PyMongoCursor


# ----------------------------------------------------------------------------------------------------------------------
# 自定义类型
#

class SchemaOperator(object):
    repr = None

    def __init__(self, *args):
        assert self.repr is not None
        self.operands = []
        for arg in args:
            if isinstance(arg, (list, tuple)):
                self.operands = self.operands + arg
            else:
                self.operands.append(arg)

    def __repr__(self):
        return str(self)

    def __iter__(self):
        for operand in self.operands:
            yield operand

    def __eq__(self, other):
        return type(self) == type(other) and self.operands == other.operands

    def validate(self, value):
        raise NotImplementedError


class IN(SchemaOperator):
    repr = 'in'

    def __init__(self, *args):
        super(IN, self).__init__(*args)

    def __str__(self):
        return "<%s " % self.repr + ', '.join([repr(i) for i in self.operands]) + '>'

    def validate(self, value):
        if value in self.operands:
            for op in self.operands:
                if value == op and isinstance(value, type(op)):
                    return True
        return False


# ----------------------------------------------------------------------------------------------------------------------
# Constants
#

# Field which does not need to be declared into the structure
STRUCTURE_KEYWORDS = ['_id', '_ns', '_revision', '_version']

# 字段允许使用的类型
AUTHORIZED_TYPES = [
    bool,
    int,
    long,
    float,
    unicode,
    str,
    datetime,
    ObjectId,
    Binary
]


# ----------------------------------------------------------------------------------------------------------------------
# Exceptions
#

class MongoSupportError(Exception):
    pass


class DataError(MongoSupportError):
    """
    数据内容与数据定义不符.
    """
    pass


class ValidationError(MongoSupportError):
    """
    数据内容无法通过校验器的验证.
    """
    pass


class StructureError(MongoSupportError):
    """
    数据模型的定义上的错误.
    """
    pass


class ConnectionError(MongoSupportError):
    """
    数据库连接错误.
    """
    pass


class OperationError(MongoSupportError):
    """
    操作错误.
    """
    pass


# ----------------------------------------------------------------------------------------------------------------------
# Metaclass
#

class ModelMetaclass(type):
    """
    元类, 校验数据模型是否正确定义.
    """

    def __new__(mcs, name, bases, attrs):
        if name == 'Model':
            return type.__new__(mcs, name, bases, attrs)

        # 保护字段, 使用dot notation的方式访问数据的时候, 跳过这些保护字段
        attrs['_protected_field_names'] = {'_protected_field_names', '_valid_paths'}
        # 父类及其父类的所有类属性
        for mro in bases[0].__mro__:
            attrs['_protected_field_names'] = attrs['_protected_field_names'].union(list(mro.__dict__))
        attrs['_protected_field_names'] = list(attrs['_protected_field_names'])

        # 验证数据结构
        mcs._validate_structure(attrs['structure'], name)

        # 添加保留字段
        if '_id' not in attrs['structure']:
            attrs['structure']['_id'] = ObjectId

        # 对于包含嵌套的数据结构, 如果要给内部的元素定义必填/验证器/默认值/索引等, 需要使用dot notation的方式来访问指定位置的元素
        attrs['_valid_paths'] = {k[0]: k[1] for k in mcs._walk_structure(attrs['structure'])}

        '''
        print "Init model class %s with valid paths {" % name
        for k, v in attrs['_valid_paths'].iteritems():
            print "    '%s': %s" % (k, v)
        print "}"
        '''

        # 验证其他描述符, 如必填/验证器/默认值/索引等
        mcs._validate_descriptors(attrs)

        return type.__new__(mcs, name, bases, attrs)

    @classmethod
    def _validate_structure(mcs, struct, name):
        """
        验证数据结构的合法性.
        """

        def __validate_structure(_struct, _name):
            # type
            if type(_struct) is type:
                if _struct not in AUTHORIZED_TYPES:
                    if _struct not in AUTHORIZED_TYPES:
                        raise StructureError("%s: %s is not an authorized type" % (_name, _struct))
            # {}
            elif isinstance(_struct, dict):
                if not len(_struct):
                    raise StructureError(
                        "%s: %s can not be a empty dict" % (_name, _struct))

                for key in _struct:
                    # Check key type
                    if isinstance(key, str):
                        if "." in key:
                            raise StructureError("%s: %s must not contain '.'" % (_name, key))
                        if key.startswith('$'):
                            raise StructureError("%s: %s must not start with '$'" % (_name, key))
                        if key[0].isdigit():
                            raise StructureError("%s: %s must not start with digit" % (_name, key))
                    else:
                        raise StructureError("%s: %s must be a str" % (_name, key))

                    if isinstance(_struct[key], dict):
                        __validate_structure(_struct[key], "%s.%s" % (_name, key))
                    elif isinstance(_struct[key], (list, tuple)):
                        __validate_structure(_struct[key], "%s.%s" % (_name, key))
                    elif isinstance(_struct[key], SchemaOperator):
                        __validate_structure(_struct[key], "%s.%s" % (_name, key))
                    elif _struct[key] not in AUTHORIZED_TYPES:
                        raise StructureError(
                            "%s: %s should be an authorized type but %s" % (_name, key, _struct[key]))
            # []
            elif isinstance(_struct, list):
                if not len(_struct):
                    raise StructureError(
                        "%s: %s can not be a empty list" % (_name, _struct))
                if len(_struct) > 1:
                    raise StructureError(
                        "%s: %s must not have more then one type" % (_name, _struct))
                for item in _struct:
                    __validate_structure(item, _name)
            # ()
            elif isinstance(_struct, tuple):
                if not len(_struct):
                    raise StructureError(
                        "%s: %s can not be a empty tuple" % (_name, _struct))
                for item in _struct:
                    if isinstance(item, dict) or isinstance(item, list) or isinstance(item, tuple):
                        raise StructureError(
                            "%s: %s can not contains complex structure dict/list/tuple" % (_name, _struct))
                    __validate_structure(item, _name)
            # IN
            elif isinstance(_struct, SchemaOperator):
                for operand in _struct:
                    if type(operand) not in AUTHORIZED_TYPES:
                        raise StructureError("%s: %s in %s is not an authorized type (%s found)" % (
                            _name, operand, _struct, type(operand).__name__))
            else:
                raise StructureError(
                    "%s: %s is not a supported thing" % (_name, _struct))

        if struct is None:
            raise StructureError("%s.structure must not be None" % name)
        if not isinstance(struct, dict):
            raise StructureError("%s.structure must be a dict instance" % name)
        __validate_structure(struct, name)

    @classmethod
    def _walk_structure(mcs, struct):
        """
        遍历数据结构获取合法的访问路径.
        不考虑列表下标, 只考虑数据结构的嵌套关系.
        """
        for key, value in struct.iteritems():
            # {}
            if isinstance(value, dict):
                yield key, {}

                for child_key, t in mcs._walk_structure(value):
                    yield '%s.%s' % (key, child_key), t
            # []
            elif isinstance(value, list):
                yield key, []

                if isinstance(value[0], dict):
                    for child_key, t in mcs._walk_structure(value[0]):
                        yield '%s.%s' % (key, child_key), t
            # ()
            elif isinstance(value, tuple):
                yield key, ()
            # type
            else:
                yield key, value

    @classmethod
    def _is_nested_structure_in_list(mcs, valid_paths, path):
        """
        判断指定的访问路径是否是一个列表内部的嵌套结构.
        """
        tokens = path.split('.')
        if len(tokens) > 1:
            del tokens[-1]
            path = ""
            for t in tokens:
                path = ("%s.%s" % (path, t)).strip('.')
                t = valid_paths[path]
                if isinstance(t, list):
                    return True
        return False

    @classmethod
    def _validate_descriptors(mcs, attrs):
        """
        验证相关设置, 如必填/验证器/默认值/索引等.
        """
        valid_paths = attrs['_valid_paths']

        for dv in attrs.get('default_values', {}):
            if dv not in valid_paths:
                raise StructureError("Error in default_values: can't find %s in structure" % dv)
            if mcs._is_nested_structure_in_list(valid_paths, dv):
                raise StructureError(
                    "Error in default_values: can't set default values to %s which is a nested structure in list" % dv)

        for rf in attrs.get('required_fields', []):
            if rf not in valid_paths:
                raise StructureError("Error in required_fields: can't find %s in structure" % rf)
            if mcs._is_nested_structure_in_list(valid_paths, rf):
                raise StructureError(
                    "Error in required_fields: can't set required fields to %s which is a nested structure in list" %
                    rf)

        for v in attrs.get('validators', {}):
            if v not in valid_paths:
                raise StructureError("Error in validators: can't find %s in structure" % v)
            if mcs._is_nested_structure_in_list(valid_paths, v):
                raise StructureError(
                    "Error in validators: can't set validators to %s which is a nested structure in list" % v)

        # required_fields
        if attrs.get('required_fields'):
            if len(attrs['required_fields']) != len(set(attrs['required_fields'])):
                raise StructureError("duplicate required_fields : %s" % attrs['required_fields'])

        # indexes
        if attrs.get('indexes'):
            for index in attrs['indexes']:
                if index.get('check', True):
                    if 'fields' not in index:
                        raise StructureError("'fields' key must be specify in indexes")
                    for key, value in index.iteritems():
                        if key == "fields":
                            if isinstance(value, str):
                                if value not in valid_paths and value not in STRUCTURE_KEYWORDS:
                                    raise StructureError("Error in indexes: can't find %s in structure" % value)
                            elif isinstance(value, list):
                                for val in value:
                                    if isinstance(val, tuple):
                                        field, direction = val
                                        if field not in valid_paths and field not in STRUCTURE_KEYWORDS:
                                            raise StructureError(
                                                "Error in indexes: can't find %s in structure" % field)
                                        if direction not in [pymongo.DESCENDING, pymongo.ASCENDING, pymongo.OFF,
                                                             pymongo.ALL, pymongo.GEO2D, pymongo.GEOHAYSTACK,
                                                             pymongo.GEOSPHERE, pymongo.TEXT]:
                                            raise StructureError(
                                                "index direction must be INDEX_DESCENDING, INDEX_ASCENDING, INDEX_OFF, "
                                                "INDEX_ALL, INDEX_GEO2D, INDEX_GEOHAYSTACK, or INDEX_GEOSPHERE."
                                                " Got %s" % direction)  # Omit text because it's still beta
                                    else:
                                        if val not in valid_paths and val not in STRUCTURE_KEYWORDS:
                                            raise StructureError("Error in indexes: can't find %s in structure" % val)
                            else:
                                raise StructureError("fields must be a string, a list of string or tuple "
                                                     "(got %s instead)" % type(value))
                        elif key == "ttl":
                            assert isinstance(value, int)


# ----------------------------------------------------------------------------------------------------------------------
# Core
#

class Model(dict):
    """
    Model = Dict schema definition + Dict content validation + Crud for Mongodb collection
    """
    # Dict schema definition

    __metaclass__ = ModelMetaclass

    # 数据结构
    structure = None

    '''
    使用dot notations的方式在数据结构的外部设置必填/默认值/验证器,
    相比于内联的方式, 出现了行为上的歧义, 如下, 当某个列表内部包含嵌套的数据结构时,
    structure = {
        'name': unicode,
        'accounts': [{
            'no': unicode,
            'balance: float
        }]
    }
    设置字段accounts.balance的默认值时, 无法知道列表的初始长度;
    设置其为必填字段时, 又无法明确定义当accounts为空列表的时候是否需要执行必填判断;
    因此对当前版本的mongosupport, 我们不支持对一个列表内嵌套结构的字段设置必填/默认值/验证器.
    嵌套数组, 哈哈, 无解

    TODO: 可以考虑实现如下的内联模式, 无需采用dot notation的方式来设置必填/默认值/验证器, 因此也没有上述的歧义,
    structure = {
        Field('name', r=True, v=validator): unicode,
        Field('accounts', r=True): [{
            Field('no', r=True): unicode,
            Field('balance', r=True, default=0, v=validator): float
        }]
    }
    与mongoengine不同, mongoengine把嵌套的数据结构解释为另一个数据对象, 我们只是将其视为整个数据模型的一部分,
    必填和验证器的逻辑可以勉强实现一致, 但是设置默认值的逻辑则不完全相同,
    mongoengine总是可以在生成这个子数据对象的时候初始化默认值, 而mongosupport作为一个整体, 初始化的机会只有一次,
    后续想要添加子数据结构的时候, 则没有生成默认值的机制了, 除非使用自己定义的dict（牺牲代码的简洁度）或者是重载__setattr__方法

    '''

    # 必填字段
    required_fields = []

    # 字段默认值
    default_values = {}

    # 验证器
    validators = {}
    # 是否触发异常, 如果不触发, 验证错误会被保存在self.validation_errors中
    raise_validation_errors = True

    # 索引定义
    indexes = []

    # 是否使用dot notations的方式访问
    # https://docs.mongodb.com/manual/core/document/#document-dot-notation
    # <embedded document>.<field>
    # <array>.<index> or <array>.$
    use_dot_notation = True

    # 该数据模型对应的collection名字
    __collection__ = None

    # pymongo.Collection - 可以使用此字段直接调用pymongo的方法, 返回的是普通的dict对象
    # https://api.mongodb.com/python/current/tutorial.html
    collection = None

    # 当前正在访问的数据库别名, 如果为空, 相当于DEFAULT_CONNECTION_NAME
    db_alias = None

    def __init__(self, doc=None):
        """
        :param doc: a dict
        """
        super(Model, self).__init__()

        # raise_validation_errors=False时, 验证器返回的所有错误
        self.validation_errors = {}

        if doc is not None:
            for k, v in doc.iteritems():
                self[k] = v
        else:
            if self.default_values:
                self._set_default_fields(self, self.structure)

    def __str__(self):
        """
        定义输出格式.
        :return:
        """
        return "%s(%s)" % (self.__class__.__name__, dict(self))

    def validate(self):
        """
        validate the document.
        This method will verify if:
          * the doc follow the structure,
          * all required fields are filled
        Additionally, this method will process all validators.
        """
        self._validate_doc(self, self.structure)

        if self.required_fields:
            self._validate_required(self)

        if self.validators:
            self._process_validators(self)

        return False if self.validation_errors else True

    def _validate_doc(self, doc, struct, path=""):
        """
        check if doc field types match the doc field structure
        """
        if doc is None:
            return
        # type
        if type(struct) is type:
            if not isinstance(doc, struct):
                self._raise_exception(DataError, path,
                                      "%s must be an instance of %s not %s" % (
                                          path, struct.__name__, type(doc).__name__))
        # {}
        elif isinstance(struct, dict):
            if not isinstance(doc, dict):
                self._raise_exception(DataError, path,
                                      "%s must be an instance of dict not %s" % (
                                          path, type(doc).__name__))

            # For fields in doc but not in structure
            doc_struct_diff = list(set(doc).difference(set(struct)))
            bad_fields = [d for d in doc_struct_diff if d not in STRUCTURE_KEYWORDS]
            if bad_fields:
                self._raise_exception(DataError, None,
                                      "unknown fields %s in %s" % (bad_fields, type(doc).__name__))

            for key in struct:
                if key in doc:
                    self._validate_doc(doc[key], struct[key], ("%s.%s" % (path, key)).strip('.'))
        # []
        elif isinstance(struct, list):
            if not isinstance(doc, list):
                self._raise_exception(DataError, path,
                                      "%s must be an instance of list not %s" % (path, type(doc).__name__))
            for obj in doc:
                self._validate_doc(obj, struct[0], path)
        # ()
        elif isinstance(struct, tuple):
            if not isinstance(doc, list):
                self._raise_exception(DataError, path,
                                      "%s must be an instance of list not %s" % (path, type(doc).__name__))
            if len(doc) != len(struct):
                self._raise_exception(DataError, path, "%s must have %s items not %s" % (
                    path, len(struct), len(doc)))
            for i in range(len(struct)):
                self._validate_doc(doc[i], struct[i], path)
        # IN
        elif isinstance(struct, SchemaOperator):
            if not struct.validate(doc):
                self._raise_exception(DataError, path,
                                      "%s must be an instance of %s not %s" % (path, struct, type(doc).__name__))
        #
        else:
            self._raise_exception(DataError, path,
                                  "%s must be an instance of %s not %s" % (
                                      path, struct.__name__, type(doc).__name__))

    def _validate_required(self, doc):
        """
        验证必填字段
        """
        for rf in self.required_fields:
            vals = self._get_values_by_path(doc, rf)
            if not vals:
                self._raise_exception(DataError, rf, "%s is required" % rf)

    def _process_validators(self, doc):
        """
        调用预定义的validator进行校验.
        """
        for key, validators in self.validators.iteritems():
            vals = self._get_values_by_path(doc, key)
            if vals:
                if not hasattr(validators, "__iter__"):
                    validators = [validators]
                for val in vals:
                    for validator in validators:
                        try:
                            if not validator(val):
                                raise ValidationError("%s does not pass the validator " + validator.__name__)
                        except Exception, e:
                            self._raise_exception(ValidationError, key, unicode(e) % key)

    def _raise_exception(self, exception, field, message):
        """
        处理异常.
        """
        if self.raise_validation_errors:
            raise exception(message)
        else:
            if field not in self.validation_errors:
                self.validation_errors[field] = []
            self.validation_errors[field].append(exception(message))

    def _get_values_by_path(self, doc, path):
        """
        获取指定路径的所有值, 会递归进去列表内部.
        """
        vals = [doc]
        for key in path.split('.'):
            # print 'getting values by path %s from %s' % (key, vals)
            new_vals = []
            for val in vals:
                if val is None or key not in val:
                    continue
                val = val[key]
                if isinstance(val, list):
                    for v in val:
                        new_vals.append(v)
                else:
                    new_vals.append(val)
            vals = new_vals

        return vals

    def _set_default_fields(self, doc, struct, path=""):
        """
        设置字段的默认值.
        """
        for key in struct:
            new_path = ("%s.%s" % (path, key)).strip('.')
            # print "setting default value for %s" % new_path

            # type
            if type(struct[key]) is type:
                if new_path in self.default_values and key not in doc:
                    new_value = self.default_values[new_path]
                    if callable(new_value):
                        new_value = new_value()
                    doc[key] = new_value

            # {}
            if isinstance(struct[key], dict):
                # 设置整个字典字段的默认值
                if new_path in self.default_values and key not in doc:
                    new_value = self.default_values[new_path]
                    if callable(new_value):
                        new_value = new_value()
                    elif isinstance(new_value, dict):
                        new_value = deepcopy(new_value)
                    doc[key] = new_value
                # 递归处理字典字段
                if [i for i in self.default_values if i.startswith("%s." % new_path)]:
                    if key not in doc or doc[key] is None:
                        doc[key] = {}
                    self._set_default_fields(doc[key], struct[key], new_path)

            # []
            if isinstance(struct[key], list):
                # 设置整个列表字段的默认值
                # 无需再递归进列表内部设置默认值, 因为无法初始化列表的元素个数
                if new_path in self.default_values and key not in doc:
                    new_value = self.default_values[new_path]
                    if callable(new_value):
                        new_value = new_value()
                    elif isinstance(new_value, list):
                        new_value = new_value[:]
                    doc[key] = new_value

    def __setattr__(self, key, value):
        """
        Support dot notation.

        注意:
        由于在数据模型这个级别有可能定义一些额外的属性, 因此此处限定只有在structure中定义的字段才会当成数据的内容来处理,
        如果写错了数据字段的名字, 会被当成一个实例的属性, 而不是数据的内容,
        后续的数据结构的校验逻辑中, 由于没有数据, 也无法验证.

        """
        if self.use_dot_notation and key not in self._protected_field_names and key in self.structure:
            # print "proxy setting attr %s with %s" % (key, value)
            self[key] = value
        else:
            dict.__setattr__(self, key, value)

    def __getattr__(self, key):
        """
        Support dot notation.
        """
        if self.use_dot_notation and key not in self._protected_field_names and key in self.structure:
            s = self.structure[key]
            found = self.get(key, None)
            # print "getting attr %s with type %s = %s" % (key, type(s).__name__, found)
            if not found:
                if isinstance(s, dict):
                    found = {}
                elif isinstance(s, list):
                    found = []
                else:
                    found = None
                self[key] = found

            return proxywrapper(found, s)
        else:
            return dict.__getattribute__(self, key)

    #
    #
    # Class level pymongo api
    #
    #

    @classmethod
    def get_collection(cls, **kwargs):
        """
        Returns the collection for the document.
        可以在此处为collection重置read_preference/write_concern等参数
        """
        if kwargs.get('refresh', False) or not hasattr(cls, 'collection') or cls.collection is None:
            db = get_db(cls.db_alias if cls.db_alias else DEFAULT_CONNECTION_NAME)

            read_preference = kwargs.get("read_preference") or ReadPreference.PRIMARY
            write_concern = kwargs.get("write_concern") or WriteConcern(w=1)

            collection_name = cls.__collection__
            cls.collection = db[collection_name].with_options(read_preference=read_preference,
                                                              write_concern=write_concern)

        return cls.collection

    @classmethod
    def _create_indexes(cls):
        """
        暂不支持创建索引.
        """
        pass

    @classmethod
    def insert_one(cls, doc, *args, **kwargs):
        """
        Please note we do not apply validation here.
        """
        collection = cls.get_collection(**kwargs)
        # InsertOneResult
        return collection.insert_one(doc, *args, **kwargs)

    @classmethod
    def insert_many(cls, docs, *args, **kwargs):
        """
        Please note we do not apply validation here.
        """
        collection = cls.get_collection(**kwargs)
        # InsertManyResult
        return collection.insert_many(docs, *args, **kwargs)

    @classmethod
    def find_one(cls, filter_or_id=None, *args, **kwargs):
        collection = cls.get_collection(**kwargs)
        doc = collection.find_one(filter_or_id, *args, **kwargs)
        if doc:
            return cls(doc)
        else:
            return None

    @classmethod
    def find(cls, *args, **kwargs):
        """
        查找多个数据模型, 参数可以参考
        https://api.mongodb.com/python/current/api/pymongo/collection.html
        """
        collection = cls.get_collection(**kwargs)
        return ModelCursor(cls, collection, *args, **kwargs)

    @classmethod
    def count(cls, filter=None, **kwargs):
        collection = cls.get_collection(**kwargs)
        return collection.count(filter, **kwargs)

    @classmethod
    def replace_one(cls, filter, replacement, *args, **kwargs):
        """
        Please note we do not apply validation here.
        """
        collection = cls.get_collection(**kwargs)
        # UpdateResult
        return collection.replace_one(filter, replacement, *args, **kwargs)

    @classmethod
    def update_one(cls, filter, update, *args, **kwargs):
        """
        Please note we do not apply validation here.
        """
        collection = cls.get_collection(**kwargs)
        # UpdateResult
        return collection.update_one(filter, update, *args, **kwargs)

    @classmethod
    def update_many(cls, filter, update, *args, **kwargs):
        """
        Please note we do not apply validation here.
        """
        collection = cls.get_collection(**kwargs)
        # UpdateResult
        return collection.update_many(filter, update, *args, **kwargs)

    @classmethod
    def delete_one(cls, filter, **kwargs):
        collection = cls.get_collection(**kwargs)
        # DeleteResult
        return collection.delete_one(filter)

    @classmethod
    def delete_many(cls, filter, **kwargs):
        collection = cls.get_collection(**kwargs)
        # DeleteResult
        return collection.delete_many(filter)

    @classmethod
    def aggregate(cls, pipeline, **kwargs):
        collection = cls.get_collection(**kwargs)
        return collection.aggregate(pipeline, **kwargs)

    @classmethod
    def distinct(cls, key, filter=None, **kwargs):
        collection = cls.get_collection(**kwargs)
        return collection.distinct(key, filter, **kwargs)

    @classmethod
    def group(cls, key, condition, initial, reduce, finalize=None, **kwargs):
        collection = cls.get_collection(**kwargs)
        return collection.group(key, condition, initial, reduce, finalize, **kwargs)

    #
    #
    # Instance level pymongo api
    #
    #

    def save(self, **kwargs):
        if not self.validate():
            raise OperationError(
                "It is an illegal %s object with errors, %s" % (self.__class__.__name__, self.validation_errors))

        collection = self.get_collection(**kwargs)
        _id = self.get('_id', None)
        if not _id:
            # InsertOneResult
            return collection.insert_one(self)
        else:
            # UpdateResult
            return collection.replace_one({'_id': _id}, self)

    def reload(self, **kwargs):
        existing = self.find_one({'_id': self['_id']}, **kwargs)
        if not existing:
            raise OperationError("Can not load existing document by %s" % self['_id'])

        self.clear()
        for k, v in existing.iteritems():
            self[k] = v

        self.validation_errors = {}

    def delete(self, **kwargs):
        collection = self.get_collection(**kwargs)
        # DeleteResult
        return collection.delete_one({'_id': self['_id']})

    def foobar(self):
        pass


# ----------------------------------------------------------------------------------------------------------------------
# Cursor - Wrap pymongo.cursor to return mongosupport objects
#

class ModelCursor(PyMongoCursor):
    def __init__(self, document_class, collection, *args, **kwargs):
        self._document_class = document_class
        super(ModelCursor, self).__init__(collection, *args, **kwargs)

    def next(self):
        return self._document_class(super(ModelCursor, self).next())

    def __next__(self):
        return self._document_class(super(ModelCursor, self).__next__())

    def __getitem__(self, index):
        if isinstance(index, slice):
            return super(ModelCursor, self).__getitem__(index)
        else:
            return self._document_class(super(ModelCursor, self).__getitem__(index))


# ----------------------------------------------------------------------------------------------------------------------
# Connection - Support multiple database
#

DEFAULT_CONNECTION_NAME = 'default'

# {alias:setting parameters dict}
_connection_settings = {}
# {alias:instance of pymongo.MongoClient}
_connections = {}
# {alias:database of pymongo.Database}
_dbs = {}


def _register_connection(alias, name=None, host=None, port=None,
                         read_preference=ReadPreference.PRIMARY,
                         username=None, password=None, authentication_source=None,
                         **kwargs):
    """
    注册数据库的连接字符串
    Add a connection.
    :param alias: the name that will be used to refer to this connection throughout MongoSupport
    :param name: the name of the specific database to use
    :param host: the host name of the :program:`mongod` instance to connect to
    :param port: the port that the :program:`mongod` instance is running on
    :param read_preference: The read preference for the collection
    :param username: username to authenticate with
    :param password: password to authenticate with
    :param authentication_source: database to authenticate against
    :param kwargs: allow ad-hoc parameters to be passed into the pymongo driver
    """
    global _connection_settings

    conn_settings = {
        'name': name or 'test',
        'host': host or 'localhost',
        'port': port or 27017,
        'read_preference': read_preference,
        'username': username,
        'password': password,
        'authentication_source': authentication_source
    }

    conn_host = conn_settings['host']
    if '://' in conn_host:
        uri_dict = uri_parser.parse_uri(conn_host)
        # Connection parameters in host url will replace the ones in conn_settings
        conn_settings.update({
            'name': uri_dict.get('database') or name,
            'username': uri_dict.get('username'),
            'password': uri_dict.get('password'),
            'read_preference': read_preference,
        })
        uri_options = uri_dict['options']
        if 'replicaset' in uri_options:
            conn_settings['replicaSet'] = True
        if 'authsource' in uri_options:
            conn_settings['authentication_source'] = uri_options['authsource']

    conn_settings.update(kwargs)
    _connection_settings[alias] = conn_settings


def _get_connection(alias=DEFAULT_CONNECTION_NAME, reconnect=False):
    """
    获取数据路连接
    """
    global _connections

    if reconnect:
        disconnect(alias)

    if alias not in _connections:
        if alias not in _connection_settings:
            msg = 'Connection with alias "%s" has not been defined' % alias
            if alias == DEFAULT_CONNECTION_NAME:
                msg = 'You have not defined a default connection'
            raise ConnectionError(msg)
        # Check existing connections that can be shared for current alias
        conn_settings = _connection_settings[alias].copy()
        conn_settings.pop('name', None)
        conn_settings.pop('username', None)
        conn_settings.pop('password', None)
        conn_settings.pop('authentication_source', None)

        if 'replicaSet' in conn_settings:
            # Discard port since it can't be used on MongoReplicaSetClient
            conn_settings.pop('port', None)
            # Discard replicaSet if not base string
            if not isinstance(conn_settings['replicaSet'], basestring):
                conn_settings.pop('replicaSet', None)

        """
        Every MongoClient instance has a built-in connection pool.
        The client instance opens one additional socket per server for monitoring the server’s state.
        """
        connection_class = MongoClient

        try:
            connection = None
            # Check for shared connections
            connection_settings_iterator = (
                (db_alias, settings.copy()) for db_alias, settings in _connection_settings.iteritems())
            for db_alias, connection_settings in connection_settings_iterator:
                connection_settings.pop('name', None)
                connection_settings.pop('username', None)
                connection_settings.pop('password', None)
                connection_settings.pop('authentication_source', None)
                if conn_settings == connection_settings and _connections.get(db_alias, None):
                    connection = _connections[db_alias]
                    break

            _connections[alias] = connection if connection else connection_class(**conn_settings)
        except Exception, e:
            raise ConnectionError("Cannot connect to database %s :\n%s" % (alias, e))
    return _connections[alias]


def get_db(alias=DEFAULT_CONNECTION_NAME, reconnect=False):
    """
    获取数据库实例
    """
    global _dbs

    if reconnect:
        disconnect(alias)

    if alias not in _dbs:
        conn = _get_connection(alias)
        conn_settings = _connection_settings[alias]
        db = conn[conn_settings['name']]
        # Authenticate if necessary
        if conn_settings['username'] and conn_settings['password']:
            db.authenticate(conn_settings['username'],
                            conn_settings['password'],
                            source=conn_settings['authentication_source'])
        _dbs[alias] = db
    return _dbs[alias]


def connect(db=None, alias=DEFAULT_CONNECTION_NAME, **kwargs):
    """
    Connect to the database specified by the 'db' argument.
    Connection settings may be provided here as well if the database is not running on the default port on localhost.
    If authentication is needed, provide username and password arguments as well.

    Multiple databases are supported by using aliases. Provide a separate `alias` to connect to different MongoClient.
    """
    global _connections
    if alias not in _connections:
        _register_connection(alias, db, **kwargs)
    return _get_connection(alias)


def disconnect(alias=DEFAULT_CONNECTION_NAME):
    """
    断开数据库连接
    """
    global _connections
    global _dbs

    if alias in _connections:
        _get_connection(alias=alias).close()
        del _connections[alias]
    if alias in _dbs:
        del _dbs[alias]


# ----------------------------------------------------------------------------------------------------------------------
# Proxy - 使用代理机制来支持dot notation的方式来访问, 不会改变内部结构, 只是在访问的时候创建轻量级的proxy对象
#

class DotDictProxy(MutableMapping, object):
    """
    A proxy for a dictionary that allows attribute access to underlying keys.
    """

    def __init__(self, obj, struct):
        self._obj_ = obj
        self._struct_ = struct

    def __getattr__(self, key):
        if key in ['_obj_', '_struct_']:
            return object.__getattribute__(self, key)

        s = self._struct_[key]
        found = self._obj_.get(key, None)
        # print "dict proxy getting attr %s with type %s = %s" % (key, type(s).__name__, found)
        if not found:
            if isinstance(s, dict):
                found = {}
            elif isinstance(s, list):
                found = []
            else:
                found = None
            self._obj_[key] = found

        return proxywrapper(found, s)

    def __setattr__(self, key, value):
        if key in ['_obj_', '_struct_']:
            return object.__setattr__(self, key, value)
        # print "dict proxy setting attr %s with %s" % (key, value)
        s = self._struct_[key]  # Just ensure key is valid
        self._obj_[key] = value

    def __delitem__(self, key):
        del self._obj_[key]

    def __len__(self):
        return self._obj_.__len__()

    def __iter__(self):
        return self._obj_.__iter__()

    def __str__(self):
        return "DotDictProxy(%s)" % self._obj_.__str__()

    __setitem__ = __setattr__
    __getitem__ = __getattr__


class DotListProxy(MutableSequence, object):
    """
    A proxy for a list that allows for wrapping items.
    """

    def __init__(self, obj, struct):
        self._obj_ = obj
        self._struct_ = struct

    def __getitem__(self, index):
        return proxywrapper(self._obj_[index], self._struct_[0])

    def __setitem__(self, index, value):
        self._obj_[index] = value

    def __delitem__(self, index):
        del self._obj_[index]

    def insert(self, index, value):
        return self._obj_.insert(index, value)

    def __len__(self):
        return self._obj_.__len__()

    def __str__(self):
        return "DotListProxy(%s)" % self._obj_.__str__()


def proxywrapper(value, struct):
    """
    The top-level API for wrapping an arbitrary object.
    """
    if isinstance(value, dict):
        return DotDictProxy(value, struct)
    if isinstance(value, list):
        return DotListProxy(value, struct)
    return value
