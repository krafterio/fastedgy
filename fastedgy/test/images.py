# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from pathlib import Path
from typing import Any

import pyvips


def solid_image(size: tuple[int, int] = (64, 64), color: tuple[int, ...] = (255, 0, 0)) -> pyvips.Image:
    """An image of one colour, its bands those of ``color`` (3 for RGB, 4 for RGBA, 1 for grey)."""
    width, height = size

    return (pyvips.Image.black(width, height, bands=len(color)) + list(color)).cast("uchar")


def encoded_image(
    size: tuple[int, int] = (64, 64), image_format: str = "png", color: tuple[int, ...] = (255, 0, 0), **options: Any
) -> bytes:
    """An image of one colour, encoded as ``image_format`` (png, jpg, webp, gif)."""
    return solid_image(size, color).write_to_buffer(f".{image_format}", **options)


def opened_image(data: bytes | str | Path) -> pyvips.Image:
    """The image ``data`` holds, or the one at a path."""
    if isinstance(data, bytes):
        return pyvips.Image.new_from_buffer(data, "")

    return pyvips.Image.new_from_file(str(data))


def described_image(data: bytes | str | Path) -> tuple[str, tuple[int, int]]:
    """The format of an image (``WEBP``, ``PNG``, ``JPEG``, ``GIF``) and its size."""
    image = opened_image(data)

    return str(image.get("vips-loader")).split("load", 1)[0].upper(), (image.width, image.height)


__all__ = [
    "described_image",
    "encoded_image",
    "opened_image",
    "solid_image",
]
