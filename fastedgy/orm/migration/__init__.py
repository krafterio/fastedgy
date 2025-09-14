# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from .view_model import *
from .enum import *
from .vector import *


def fastedgy_process_revision_directives(context, revision, directives):
    """
    Post-process migration directives to fix column definitions and handle extensions.
    This runs after all operations are generated but before writing the migration file.
    """
    if not directives:
        return

    if not directives[0].upgrade_ops:
        return

    process_enum_revision_directives(context, revision, directives)
    process_vector_revision_directives(context, revision, directives)


__all__ = [
    "fastedgy_process_revision_directives",
    "process_enum_revision_directives",
    "process_vector_revision_directives",
    "enable_vector_extension",
    "disable_vector_extension",
]
