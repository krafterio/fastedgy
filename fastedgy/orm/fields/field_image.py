# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from dataclasses import dataclass
from typing import Any, Literal, overload

from .field_file import FileField


@dataclass(frozen=True)
class StoredImage:
    """How an image is rewritten before it is stored: its longest side brought to ``max_side`` at most, encoded in
    ``format`` at ``quality``, set upright and stripped of its metadata. ``max_pixels`` is the largest image decoded."""

    max_side: int = 2560
    format: str = "webp"
    quality: int = 85
    max_pixels: int = 250_000_000


class ImageField(FileField):
    """A stored image, optimized by the storage before it is written (see StoredImage)."""

    @overload
    def __new__(
        cls,
        *args: Any,
        max_side: int = ...,
        quality: int = ...,
        null: Literal[True],
        **kwargs: Any,
    ) -> str | None: ...

    @overload
    def __new__(
        cls,
        *args: Any,
        max_side: int = ...,
        quality: int = ...,
        null: Literal[False] = False,
        **kwargs: Any,
    ) -> str: ...

    def __new__(cls, *args: Any, max_side: int = 2560, quality: int = 85, **kwargs: Any) -> Any:
        return super().__new__(cls, *args, stored_image=StoredImage(max_side=max_side, quality=quality), **kwargs)


def stored_image_of(model_cls: Any, field: str) -> StoredImage | None:
    """The optimization of a model field, None when it is no ImageField."""
    model_field = model_cls.meta.fields.get(field)

    return getattr(model_field, "stored_image", None) if isinstance(model_field, ImageField) else None


__all__ = [
    "ImageField",
    "StoredImage",
    "stored_image_of",
]
