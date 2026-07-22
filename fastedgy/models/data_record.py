# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n import _ts
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields


class DataRecord(BaseModel):
    class Meta:
        tablename = "data_records"

    key: str = fields.CharField(max_length=255, unique=True, index=True, label=_ts("Key"))

    model: str = fields.CharField(max_length=255, index=True, label=_ts("Model"))

    record_id: int = fields.IntegerField(label=_ts("Record ID"))


__all__ = [
    "DataRecord",
]
