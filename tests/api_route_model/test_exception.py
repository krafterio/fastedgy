# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from fastedgy.api_route_model.exception import handle_action_exception
from fastedgy.app import FastEdgy
from fastedgy.test.models.course import Course


def _detail(message: str, model_cls: type | None = Course) -> str:
    with pytest.raises(HTTPException) as raised:
        handle_action_exception(IntegrityError("INSERT", {}, Exception(message)), model_cls)

    return str(raised.value.detail)


async def test_a_violation_names_the_fields_by_their_label(setup_openapi_app: FastEdgy) -> None:
    unique = 'duplicate key value violates unique constraint "uq"\nDETAIL:  Key (code, title)=(C1, x) already exists.'
    not_null = 'null value in column "code" of relation "test_courses" violates not-null constraint'

    assert _detail(unique) == "An entry with this value already exists for the field 'Code, Title'."
    assert _detail(not_null) == "A required field is missing: 'Code'."
    assert _detail(not_null, None) == "A required field is missing: 'code'."
