# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""
Relation operations for ManyToMany and OneToMany fields.

This module provides a tuple-based API for managing relations:
- ["create", {...}] - Create and link a new record
- ["update", {"id": ..., ...}] - Update and ensure link
- ["link", 42] - Link existing record
- ["unlink", 42] - Remove relation (keep record)
- ["delete", 42] - Delete record (remove relation)
- ["set", [1, 2, 3]] - Replace all relations
- ["clear"] - Remove all relations
"""

from fastedgy.orm.relations.operations import (
    CreateOp,
    UpdateOp,
    DeleteOp,
    UnlinkOp,
    LinkOp,
    SetOp,
    ClearOp,
    RelationOperation,
)
from fastedgy.orm.relations.utils import (
    extract_id,
    extract_id_and_values,
    RelationOperationError,
)
from fastedgy.orm.relations.processor import (
    process_many_to_many_operations,
)

__all__ = [
    # Operations
    "CreateOp",
    "UpdateOp",
    "DeleteOp",
    "UnlinkOp",
    "LinkOp",
    "SetOp",
    "ClearOp",
    "RelationOperation",
    # Utils
    "extract_id",
    "extract_id_and_values",
    "RelationOperationError",
    # Processor
    "process_many_to_many_operations",
]
