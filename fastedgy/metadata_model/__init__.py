# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.metadata_model.registry import (
    TypeMetadataModels,
    TypeMapMetadataModels,
    MetadataModelRegistry,
)
from fastedgy.metadata_model.decorators import metadata_model


__all__ = [
    "metadata_model",
    "TypeMetadataModels",
    "TypeMapMetadataModels",
    "MetadataModelRegistry",
]
