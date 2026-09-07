# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.orm.fields.field_choice import ExtendableChoiceEnum


class WorkspaceExtraFieldModel(ExtendableChoiceEnum):
    """The models a workspace may add a field to.

    Never written by hand: a model joins the list by holding the `extra` JSON
    column, which `ExtendableMixin` is the shortest way to bring."""


__all__ = [
    "WorkspaceExtraFieldModel",
]
