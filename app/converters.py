# -*- coding: utf-8 -*-
"""
    converters.py
    ~~~~~~~~~~~~~~

    自定义的转换器

    :copyright: (c) 2016 by fengweimin.
    :date: 16/5/17
"""

from werkzeug.routing import BaseConverter


class ListConverter(BaseConverter):
    """
    自定义URL转换器, 允许传入列表

    /price/US+CN
    ->
    @app.route('/price/<list:countries>')

    """

    def to_python(self, value):
        """
        用于转换路径成一个Python对象，并传递给视图函数
        """
        return value.split('+')

    def to_url(self, values):
        """
        被url_for()调用，来转换参数成为符合URL的形式
        """
        return '+'.join(BaseConverter.to_url(value)
                        for value in values)
