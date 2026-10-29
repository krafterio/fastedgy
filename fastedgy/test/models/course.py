# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.api_route_model import api_route_model
from fastedgy.models.base import BaseModel
from fastedgy.models.mixins import SearchableMixin
from fastedgy.orm import fields
from fastedgy.test.models.category import Category


@api_route_model()
class Course(BaseModel, SearchableMixin):
    code = fields.CharField(max_length=20)
    title = fields.CharField(max_length=40, translatable=True)
    summary = fields.TextField(null=True, translatable=True)
    body = fields.RichTextField(null=True, translatable=True, searchable=False)
    category = fields.ForeignKey(Category, null=True, related_name="courses")

    class Meta(BaseModel.Meta, SearchableMixin.Meta):
        tablename = "test_courses"


__all__ = [
    "Course",
]
