# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.metadata_model.decorators import metadata_model
from fastedgy.metadata_model.registry import (
    MetadataModelRegistry,
    TypeMapMetadataModels,
    TypeMetadataModels,
)

__all__ = [
    "MetadataModelRegistry",
    "TypeMapMetadataModels",
    "TypeMetadataModels",
    "metadata_model",
]
