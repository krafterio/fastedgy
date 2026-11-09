# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io
import subprocess
import sys

import pytest
import pyvips
from starlette.datastructures import Headers, UploadFile

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.storage import Storage, StoredImage
from fastedgy.test.images import described_image, encoded_image, opened_image, solid_image


def _upload(data: bytes, filename: str, content_type: str) -> UploadFile:
    return UploadFile(
        io.BytesIO(data), size=len(data), filename=filename, headers=Headers({"content-type": content_type})
    )


async def _optimized(data: bytes, filename: str, content_type: str, image: StoredImage | None = None) -> UploadFile:
    upload = _upload(data, filename, content_type)
    await get_service(Storage).optimize_upload(upload, image or StoredImage())

    return upload


async def _reread(upload: UploadFile) -> bytes:
    await upload.seek(0)

    return await upload.read()


async def test_a_large_photo_is_brought_to_webp_within_its_longest_side(setup_db: FastEdgy) -> None:
    upload = await _optimized(encoded_image((3000, 1500), "jpg"), "photo.jpg", "image/jpeg")

    assert described_image(await upload.read()) == ("WEBP", (2560, 1280))
    assert (upload.filename, upload.content_type) == ("photo.webp", "image/webp")
    assert upload.size == len(await _reread(upload))


async def test_a_turned_photo_is_set_upright_and_loses_its_metadata(setup_db: FastEdgy) -> None:
    photo = solid_image((100, 50), (0, 0, 255)).copy()
    photo.set_type(pyvips.GValue.gint_type, "orientation", 6)
    photo.set_type(pyvips.GValue.gstr_type, "exif-ifd0-Make", "Camera")

    upload = await _optimized(photo.jpegsave_buffer(), "photo.jpg", "image/jpeg")
    stored = opened_image(await upload.read())

    assert (stored.width, stored.height) == (50, 100)
    assert not {"exif-data", "orientation", "xmp-data"} & set(stored.get_fields())


async def test_an_animated_image_is_stored_as_is(setup_db: FastEdgy) -> None:
    frames = pyvips.Image.arrayjoin([solid_image((20, 20), (255, 0, 0)), solid_image((20, 20), (0, 0, 255))], across=1)
    frames = frames.copy()
    frames.set_type(pyvips.GValue.gint_type, "page-height", 20)
    data = frames.gifsave_buffer()

    upload = await _optimized(data, "loop.gif", "image/gif")

    assert await upload.read() == data
    assert (upload.filename, upload.content_type) == ("loop.gif", "image/gif")


async def test_a_file_that_is_no_image_is_stored_as_is(setup_db: FastEdgy) -> None:
    upload = await _optimized(b"%PDF-1.4 not an image", "doc.pdf", "application/pdf")

    assert await upload.read() == b"%PDF-1.4 not an image"
    assert upload.filename == "doc.pdf"


async def test_an_image_already_optimized_is_stored_as_is(setup_db: FastEdgy) -> None:
    data = encoded_image((300, 200), "webp", keep=pyvips.enums.ForeignKeep.NONE)

    upload = await _optimized(data, "small.webp", "image/webp")

    assert await upload.read() == data


async def test_an_image_past_its_own_ceiling_is_refused(setup_db: FastEdgy) -> None:
    with pytest.raises(ValueError):
        await _optimized(encoded_image((40, 30)), "huge.png", "image/png", StoredImage(max_pixels=1000))


async def test_a_transparent_image_keeps_its_transparency(setup_db: FastEdgy) -> None:
    upload = await _optimized(encoded_image((3000, 1500), color=(255, 0, 0, 0)), "logo.png", "image/png")
    stored = opened_image(await upload.read())

    assert (stored.width, stored.height) == (2560, 1280)
    assert stored.hasalpha() and stored[3].max() == 0


_HUGE_PNG = """
import io, resource, sys, time
import pyvips
from fastedgy.orm.fields import StoredImage
from fastedgy.storage.services import Storage

data = (pyvips.Image.black(17320, 11547, bands=3) + [200, 30, 60]).cast("uchar").pngsave_buffer(compression=1)
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
start = time.monotonic()
_, _, size = Storage.__new__(Storage)._optimize_image(io.BytesIO(data), StoredImage())
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(size[0], size[1], time.monotonic() - start, (peak - before) * (1 if sys.platform == "darwin" else 1024))
"""


def test_a_200_megapixel_png_is_optimized_quickly_in_little_memory() -> None:
    output = subprocess.run([sys.executable, "-c", _HUGE_PNG], capture_output=True, text=True, check=True).stdout
    width, height, seconds, grown = output.split()

    assert (int(width), int(height)) == (2560, 1707)
    assert float(seconds) < 5
    assert int(grown) < 600 * 1024**2
