# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import base64
import io
import logging
import mimetypes
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

from anyio import to_thread
from jose import JWTError, jwt
from starlette.datastructures import UploadFile

from fastedgy import context
from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject, get_service
from fastedgy.http_client import create_http_client, request_with_retry
from fastedgy.i18n import _t
from fastedgy.orm import Registry
from fastedgy.storage.adapters.base import StorageAdapter, clean_storage_path
from fastedgy.storage.adapters.filesystem import FilesystemAdapter

try:
    from PIL import Image
    from PIL.Image import DecompressionBombError
except Exception:
    Image = None
    DecompressionBombError = OSError

logger = logging.getLogger("fastedgy.storage")

CACHE_PREFIX = "cache_optimized_images"

DOWNLOAD_TOKEN_TYPE = "storage-download"

DOWNLOAD_TOKEN_SECONDS = 6 * 3600

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


@dataclass(frozen=True)
class StorageUsage:
    """The stored files and the optimized images cache, each counted with its bytes."""

    data_files: int
    data_bytes: int
    cache_files: int
    cache_bytes: int


def _create_adapter(settings: BaseSettings, adapter_name: str) -> StorageAdapter:
    """Create a storage adapter from its name and settings."""
    if adapter_name == "s3":
        from fastedgy.storage.adapters.s3 import S3Adapter

        if not settings.s3_bucket:
            raise ValueError("S3_BUCKET is required when using the s3 storage adapter")

        return S3Adapter(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint=settings.s3_endpoint,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            prefix=settings.s3_prefix,
            storage_class=settings.s3_storage_class,
        )

    # Default: filesystem
    return FilesystemAdapter(root=settings.storage_data_path)


class Storage:
    def __init__(self, settings: BaseSettings = Inject(BaseSettings)):
        self.settings = settings
        self.adapter: StorageAdapter = _create_adapter(settings, settings.storage_adapter)
        self.cache_adapter: StorageAdapter = FilesystemAdapter(root=settings.storage_data_path)
        if settings.storage_cache_adapter != "filesystem":
            self.cache_adapter = _create_adapter(settings, settings.storage_cache_adapter)

    @property
    def is_filesystem(self) -> bool:
        """Check if the main adapter is filesystem-based."""
        return isinstance(self.adapter, FilesystemAdapter)

    # --------------------
    # Path helpers
    # --------------------
    def _get_workspace_prefix(self, global_storage: bool = False) -> str:
        """Return the workspace prefix for storage paths."""
        workspace = context.get_workspace()
        if workspace and not global_storage:
            folder = self.settings.storage_workspace_folder
            return f"{folder}/{workspace.id}"
        return "global"

    def _resolve_path(self, path: str, global_storage: bool = False) -> str:
        """Build a full relative path with workspace prefix."""
        prefix = self._get_workspace_prefix(global_storage)
        clean = clean_storage_path(path)
        if prefix:
            return f"{prefix}/{clean}" if clean else prefix
        return clean

    # Backward-compatible path methods (filesystem only)
    def get_base_path(self, global_storage: bool = False) -> Path:
        workspace = context.get_workspace()
        if workspace and not global_storage:
            sub = os.path.join(self.settings.storage_workspace_folder, str(workspace.id))
        else:
            sub = "global"

        return Path(os.path.join(self.settings.storage_data_path, sub))

    def get_directory_path(self, path: str, ensure_exists: bool = True, global_storage: bool = False) -> Path:
        dir_path = self.get_base_path(global_storage)

        safe_custom_path = Path(clean_storage_path(path)).parts
        dir_path = dir_path.joinpath(*safe_custom_path)

        if ensure_exists:
            os.makedirs(dir_path, exist_ok=True)

        return dir_path

    def get_file_path(self, path: str, ensure_exists: bool = True, global_storage: bool = False) -> Path:
        path_parts = Path(clean_storage_path(path)).parts
        directory_path = ""
        filename = path

        if len(path_parts) > 0:
            filename = path_parts[-1]
            directory_parts = path_parts[:-1]

            if directory_parts:
                directory_path = "/".join(directory_parts)

        directory_path = self.get_directory_path(directory_path, ensure_exists, global_storage)

        return directory_path.joinpath(filename)

    def get_relative_path(self, file_path: Path, global_storage: bool = False) -> str:
        data_path = self.get_base_path(global_storage)

        return str(file_path.relative_to(data_path))

    # --------------------
    # Adapter-based file operations
    # --------------------
    async def file_exists(self, relative_path: str, global_storage: bool = False) -> bool:
        """Check if a file exists in storage."""
        full_path = self._resolve_path(relative_path, global_storage)
        return await self.adapter.exists(full_path)

    async def file_size(self, relative_path: str, global_storage: bool = False) -> int:
        """Get the size of a file in storage."""
        full_path = self._resolve_path(relative_path, global_storage)
        return await self.adapter.file_size(full_path)

    async def read_file(self, relative_path: str, global_storage: bool = False) -> bytes:
        """Read a file from storage."""
        full_path = self._resolve_path(relative_path, global_storage)
        return await self.adapter.read(full_path)

    async def stream_file(
        self,
        relative_path: str,
        global_storage: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        """Stream a file from storage."""
        full_path = self._resolve_path(relative_path, global_storage)
        async for chunk in self.adapter.read_stream(full_path, chunk_size):
            yield chunk

    # --------------------
    # Image optimization
    # --------------------
    def _get_image_quality(self) -> int:
        try:
            q = int(getattr(self.settings, "image_quality", 80))
        except Exception:
            q = 80
        return max(1, min(100, q))

    def _get_max_image_pixels(self) -> int | None:
        """Optional budget, stricter than Pillow's own ceiling. A value above it
        changes nothing: Image.open refuses the file first."""
        try:
            value = getattr(self.settings, "image_max_pixels", None)
            return int(value) if value else None
        except Exception:
            return None

    def _probe_image(self, file: BinaryIO) -> tuple[int | None, int | None]:
        """Read the header without decoding: Image.open parses the dimensions
        only, and is where Pillow's own decompression-bomb ceiling fires. Bytes
        that are not an image open with an error and are stored untouched, so
        the budget holds whatever extension or mime type the caller announced."""
        if Image is None:
            return None, None

        try:
            with Image.open(file) as img:
                width, height = img.size
        except DecompressionBombError:
            raise ValueError(_t("This image holds too many pixels to be processed"))
        except Exception:
            return None, None

        limit = self._get_max_image_pixels()
        if limit and width * height > limit:
            raise ValueError(
                _t(
                    "This image is too large: {width}x{height} pixels, {limit} maximum",
                    width=width,
                    height=height,
                    limit=limit,
                )
            )

        return width, height

    def _inspect(self, file: BinaryIO) -> tuple[int | None, int | None, int]:
        file.seek(0)
        width, height = self._probe_image(file)
        size = file.seek(0, os.SEEK_END)
        file.seek(0)

        return width, height, size

    def _get_cache_path(self, path: str, global_storage: bool = False) -> str:
        """Return the cache-relative path for a given path."""
        workspace = context.get_workspace()
        clean = clean_storage_path(path)
        if workspace and not global_storage:
            folder = self.settings.storage_workspace_folder
            return f"{CACHE_PREFIX}/{folder}/{workspace.id}/{clean}"
        return f"{CACHE_PREFIX}/global/{clean}"

    def _is_image_path(self, path: str) -> bool:
        name = path.rsplit("/", 1)[-1] if "/" in path else path
        mime = mimetypes.guess_type(name)[0]
        return bool(mime and mime.startswith("image/"))

    def _clamp_dimensions(self, ow: int, oh: int, w: int | None, h: int | None) -> tuple[int | None, int | None]:
        cw = None if w is None else min(w, ow)
        ch = None if h is None else min(h, oh)
        return cw, ch

    def _compute_target_size(self, ow: int, oh: int, w: int | None, h: int | None, mode: str) -> tuple[int, int, str]:
        if w and not h:
            scale = w / ow
            th = round(oh * scale)
            return w, max(1, th), "contain"
        if h and not w:
            scale = h / oh
            tw = round(ow * scale)
            return max(1, tw), h, "contain"

        if not w or not h:
            return ow, oh, "contain"

        mode = "cover" if str(mode).lower() == "cover" else "contain"
        if mode == "contain":
            scale = min(w / ow, h / oh)
            tw = round(ow * scale)
            th = round(oh * scale)
            return max(1, tw), max(1, th), mode
        else:
            scale = max(w / ow, h / oh)
            tw = round(ow * scale)
            th = round(oh * scale)
            return max(1, tw), max(1, th), mode

    def _format_from_ext(self, ext: str | None, fallback: str) -> tuple[str, str]:
        e = (ext or fallback or "").lower().lstrip(".")
        if e in ("jpg", "jpeg"):
            return "JPEG", "image/jpeg"
        if e == "png":
            return "PNG", "image/png"
        if e == "webp":
            return "WEBP", "image/webp"
        if fallback in ("jpg", "jpeg"):
            return "JPEG", "image/jpeg"
        if fallback == "png":
            return "PNG", "image/png"
        if fallback == "webp":
            return "WEBP", "image/webp"
        return "JPEG", "image/jpeg"

    def _save_image_to_bytes(
        self,
        img: "PILImage",
        pil_format: str,
        quality: int,
    ) -> bytes:
        save_kwargs: dict[str, Any] = {}
        if pil_format == "JPEG":
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            save_kwargs.update({"optimize": True, "quality": quality, "progressive": True})
        elif pil_format == "PNG":
            compress_level = max(0, min(9, round((100 - quality) * 9 / 100)))
            save_kwargs.update({"optimize": True, "compress_level": compress_level})
        elif pil_format == "WEBP":
            save_kwargs.update({"quality": quality, "method": 4})

        buf = io.BytesIO()
        img.save(buf, pil_format, **save_kwargs)
        return buf.getvalue()

    async def _generate_cache_image(
        self,
        source_data: bytes,
        source_name: str,
        cache_path: str,
        *,
        w: int | None,
        h: int | None,
        mode: str,
        out_ext: str | None,
    ) -> tuple[str | None, bytes, str]:
        """Generate optimized image and save to cache.

        Returns (cache_path, image_bytes, mime_type). A None cache_path means
        no transformation was needed: nothing is written and the caller must
        serve the original file directly.
        """
        if Image is None:
            mime = mimetypes.guess_type(source_name)[0] or "application/octet-stream"
            return None, source_data, mime

        # PIL decode/resize/encode is CPU-bound: run it in a thread so a burst
        # of first-time generations does not block the event loop.
        data, mime_type = await to_thread.run_sync(
            partial(self._render_cache_image, source_data, source_name, w=w, h=h, mode=mode, out_ext=out_ext)
        )

        if data is None:
            return None, source_data, mime_type

        await self.cache_adapter.write(cache_path, data, mime_type)

        return cache_path, data, mime_type

    def _render_cache_image(
        self,
        source_data: bytes,
        source_name: str,
        *,
        w: int | None,
        h: int | None,
        mode: str,
        out_ext: str | None,
    ) -> tuple[bytes | None, str]:
        """Render the optimized variant. A None payload means no transformation
        is needed and the original must be served directly."""
        assert Image is not None

        with Image.open(io.BytesIO(source_data)) as img:
            ow, oh = img.size
            w, h = self._clamp_dimensions(ow, oh, w, h)
            tw, th, mode = self._compute_target_size(ow, oh, w, h, mode)

            src_ext = source_name.rsplit(".", 1)[-1].lower() if "." in source_name else ""
            out_format, mime_type = self._format_from_ext(out_ext, src_ext)

            if (tw, th) == (ow, oh) and out_format.lower() == src_ext.lower():
                mime = mimetypes.guess_type(source_name)[0] or mime_type
                return None, mime

            if mode == "contain":
                final_img = img.resize((tw, th), Image.Resampling.LANCZOS)
            else:
                resized = img.resize((tw, th), Image.Resampling.LANCZOS)
                cw = w or tw
                ch = h or th
                left = max(0, (tw - cw) // 2)
                top = max(0, (th - ch) // 2)
                right = left + cw
                bottom = top + ch
                final_img = resized.crop((left, top, right, bottom))

            quality = self._get_image_quality()

            return self._save_image_to_bytes(final_img, out_format, quality), mime_type

    async def get_optimized_or_original(
        self,
        source_relative_path: str,
        *,
        w: int | None = None,
        h: int | None = None,
        mode: str = "contain",
        out_ext: str | None = None,
        global_storage: bool = False,
        regenerate: bool = False,
        check_cache: bool = True,
    ) -> tuple[str, str]:
        """Return (relative_path, mime_type) for serving.

        The returned path is either the original or a cached optimized version.
        The original is not checked here: opening it raises FileNotFoundError
        when there is none. Use open_download() to actually stream the content.

        With `regenerate=True` the cache lookup is skipped and the optimized
        variant is rebuilt from the source (recovery path when a cached file
        was evicted between resolution and read).

        With `check_cache=False` the cached path is returned without asking the
        cache whether it holds it, which saves a request per download on S3: the
        caller opens it, and on FileNotFoundError resolves again with
        `regenerate=True`.
        """
        source_name = source_relative_path.rsplit("/", 1)[-1] if "/" in source_relative_path else source_relative_path
        full_source = self._resolve_path(source_relative_path, global_storage)
        source_mime = mimetypes.guess_type(source_name)[0] or "application/octet-stream"

        is_image = self._is_image_path(source_relative_path)
        options_provided = any([w, h, out_ext, (mode and mode != "contain")])

        if (not is_image) or (not options_provided):
            return source_relative_path, source_mime

        # Compute cache path
        req_w = 0 if w is None else w
        req_h = 0 if h is None else h
        mode_name = "cover" if str(mode).lower() == "cover" else "contain"

        src_ext = source_name.rsplit(".", 1)[-1].lower() if "." in source_name else ""
        out_fmt, mime_type = self._format_from_ext(out_ext, src_ext)
        out_ext_final = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(out_fmt, "jpg")

        cache_rel = self._get_cache_path(source_relative_path, global_storage)
        cache_path = f"{cache_rel}/{mode_name}_w{req_w}_h{req_h}.{out_ext_final}"

        if not regenerate and (not check_cache or await self.cache_adapter.exists(cache_path)):
            return f"__cache__:{cache_path}", mime_type

        try:
            source_data = await self.adapter.read(full_source)
        except FileNotFoundError:
            return source_relative_path, source_mime

        try:
            generated_path, _, mime_type = await self._generate_cache_image(
                source_data,
                source_name,
                cache_path,
                w=w,
                h=h,
                mode=mode,
                out_ext=out_ext if out_ext else src_ext,
            )
        except (OSError, DecompressionBombError) as e:
            # The stored bytes cannot be decoded as an image (corrupt upload,
            # exotic format, truncated file — UnidentifiedImageError is an
            # OSError), or they hold more pixels than Pillow agrees to expand
            # (DecompressionBombError derives from Exception, not OSError).
            # Serving the original is this method's contract and the client may
            # still render it; a warning on the fallback beats a 500 on every
            # display of that file.
            logger.warning(f"Cannot optimize image {source_relative_path}, serving the original: {e!r}")
            return source_relative_path, source_mime

        if generated_path is None:
            # Already at the requested size and format: serve the original,
            # nothing to cache (a __cache__ path without a file behind it
            # made every download of such an image die on FileNotFoundError).
            return source_relative_path, mime_type

        return f"__cache__:{generated_path}", mime_type

    async def _download_target(self, resolved_path: str, global_storage: bool) -> tuple[StorageAdapter, str]:
        """The adapter and the path to read. A cached variant is touched on the way, so that the age-based
        cleanup of a cache that keeps access times only removes the variants nobody reads."""
        if resolved_path.startswith("__cache__:"):
            cache_path = resolved_path[len("__cache__:") :]
            await self.cache_adapter.touch(cache_path)

            return self.cache_adapter, cache_path

        if resolved_path.startswith("__stored__:"):
            return self.adapter, resolved_path[len("__stored__:") :]

        return self.adapter, self._resolve_path(resolved_path, global_storage)

    def download_token(self, resolved_path: str, global_storage: bool = False) -> str:
        """A token opening one path from get_optimized_or_original without the caller's credentials, for an
        element the browser reads on its own and cannot give a header to, a video seeking by ranges.

        It names the stored key, resolved now in the caller's workspace, and lasts DOWNLOAD_TOKEN_SECONDS. Its
        type keeps it from ever standing for an access token."""
        cached = resolved_path.startswith("__cache__:")
        key = resolved_path[len("__cache__:") :] if cached else self._resolve_path(resolved_path, global_storage)
        payload = {
            "type": DOWNLOAD_TOKEN_TYPE,
            "key": key,
            "cache": cached,
            "exp": datetime.now(UTC) + timedelta(seconds=DOWNLOAD_TOKEN_SECONDS),
        }

        return jwt.encode(payload, self.settings.auth_secret_key, algorithm=self.settings.auth_algorithm)

    def resolve_download_token(self, token: str) -> str | None:
        """The path a download token opens, for open_download(), or None for a token forged, expired or of
        another type."""
        try:
            payload = jwt.decode(token, self.settings.auth_secret_key, algorithms=[self.settings.auth_algorithm])
        except JWTError:
            return None

        if payload.get("type") != DOWNLOAD_TOKEN_TYPE or not payload.get("key"):
            return None

        return f"{'__cache__' if payload.get('cache') else '__stored__'}:{payload['key']}"

    async def open_download(
        self,
        resolved_path: str,
        global_storage: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> tuple[int, AsyncIterator[bytes]]:
        """Open a path from get_optimized_or_original: its size and its content in chunks,
        read in one request where the adapter allows it. Raises FileNotFoundError when there is no file."""
        adapter, path = await self._download_target(resolved_path, global_storage)

        return await adapter.open_stream(path, chunk_size)

    async def open_range_download(
        self,
        resolved_path: str,
        start: int,
        end: int | None,
        global_storage: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> tuple[int, int, int, AsyncIterator[bytes]] | None:
        """Open a byte range of a path from get_optimized_or_original, end None meaning the rest of the file:
        the range served, the size of the whole file and the chunks. None when the range lies past the end of
        the file, FileNotFoundError when there is no file."""
        adapter, path = await self._download_target(resolved_path, global_storage)

        return await adapter.open_range(path, start, end, chunk_size)

    async def stream_download(
        self,
        resolved_path: str,
        global_storage: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        """Stream a file for download based on the path from get_optimized_or_original.

        Handles both cached images (via cache_adapter) and original files (via adapter).
        """
        adapter, path = await self._download_target(resolved_path, global_storage)

        async for chunk in adapter.read_stream(path, chunk_size):
            yield chunk

    async def stream_range_download(
        self,
        resolved_path: str,
        start: int,
        end: int,
        global_storage: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        """Stream a byte range of a file for download (inclusive start and end)."""
        adapter, path = await self._download_target(resolved_path, global_storage)

        async for chunk in adapter.read_range_stream(path, start, end, chunk_size):
            yield chunk

    async def get_file_size_for_download(
        self,
        resolved_path: str,
        global_storage: bool = False,
    ) -> int:
        """Get file size for a resolved path (from get_optimized_or_original)."""
        adapter, path = await self._download_target(resolved_path, global_storage)

        return await adapter.file_size(path)

    # --------------------
    # Upload operations
    # --------------------
    async def upload(
        self,
        file: UploadFile,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
        attachment_values: dict[str, Any] | None = None,
    ) -> str:
        if not file.filename:
            raise ValueError(_t("Missing filename"))

        ext = os.path.splitext(file.filename)[1].lower()[1:]
        if not ext:
            guessed = mimetypes.guess_extension(file.content_type or "") or ".bin"
            ext = guessed.lstrip(".")

        return await self._finalize_store(
            file=file.file,
            directory_path=directory_path,
            filename=filename,
            ext=ext,
            mime_type=file.content_type or None,
            global_storage=global_storage,
            original_name=file.filename,
            create_attachment=create_attachment,
            attachment_values=attachment_values,
        )

    async def upload_from_bytes(
        self,
        content: bytes,
        directory_path: str,
        filename: str | None = None,
        mime_type: str | None = None,
        extension: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
        attachment_values: dict[str, Any] | None = None,
    ) -> str:
        """Store bytes already in hand, for a caller holding the content itself
        (a duplicated attachment, a generated file) rather than an upload."""
        return await self.upload_from_file(
            io.BytesIO(content),
            directory_path=directory_path,
            filename=filename,
            mime_type=mime_type,
            extension=extension,
            global_storage=global_storage,
            create_attachment=create_attachment,
            attachment_values=attachment_values,
        )

    async def upload_from_file(
        self,
        file: BinaryIO,
        directory_path: str,
        filename: str | None = None,
        mime_type: str | None = None,
        extension: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
        attachment_values: dict[str, Any] | None = None,
    ) -> str:
        """Store an open binary file without reading it whole: the adapter
        streams it, so an upload spooled to disk never sits in memory."""
        ext = (extension or mimetypes.guess_extension(mime_type or "") or ".bin").lstrip(".")

        return await self._finalize_store(
            file=file,
            directory_path=directory_path,
            filename=filename,
            ext=ext,
            mime_type=mime_type,
            global_storage=global_storage,
            original_name=filename.replace("{ext}", ext) if filename else None,
            create_attachment=create_attachment,
            attachment_values=attachment_values,
        )

    async def upload_from_base64(
        self,
        data: str,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
        attachment_values: dict[str, Any] | None = None,
    ) -> str:
        if not data.startswith("data:"):
            raise ValueError(_t("Content is not a data URL"))

        header, base64_data = data.split(",", 1)
        content_type = header.split(";")[0][5:]

        return await self.upload_from_bytes(
            base64.b64decode(base64_data),
            directory_path=directory_path,
            filename=filename,
            mime_type=content_type or None,
            global_storage=global_storage,
            create_attachment=create_attachment,
            attachment_values=attachment_values,
        )

    async def download_and_upload(
        self,
        file_url: str,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
        attachment_values: dict[str, Any] | None = None,
    ) -> str:
        try:
            async with create_http_client() as client:
                response = await request_with_retry(client, "GET", file_url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                guessed = mimetypes.guess_extension(content_type) or ".bin"
                ext = guessed.lstrip(".")

                return await self._finalize_store(
                    file=io.BytesIO(response.content),
                    directory_path=directory_path,
                    filename=filename,
                    ext=ext,
                    mime_type=content_type or None,
                    global_storage=global_storage,
                    original_name=filename.replace("{ext}", ext) if filename else None,
                    create_attachment=create_attachment,
                    attachment_values=attachment_values,
                )
        except Exception as e:
            raise ValueError(_t("Error while downloading the file: {error}", error=str(e)))

    # --------------------
    # Delete operations
    # --------------------
    async def delete(
        self,
        file_path: str | None,
        global_storage: bool = False,
        delete_record: bool = False,
    ) -> bool:
        try:
            if not file_path:
                return True

            registry: Registry = get_service(Registry)

            try:
                if delete_record and "Attachment" in registry.models:
                    AttachmentModel: Any = registry.get_model("Attachment")
                    attachments = await AttachmentModel.query.filter(
                        storage_path=file_path,
                        is_global=global_storage,
                    ).all()
                    for att in attachments:
                        await att.delete()
            except Exception:
                pass

            # Delete the file via adapter
            full_path = self._resolve_path(file_path, global_storage)
            await self.adapter.delete(full_path)

            # Delete optimized cache (best-effort)
            try:
                cache_rel = self._get_cache_path(file_path, global_storage)
                await self.cache_adapter.delete_directory(cache_rel)
            except Exception:
                pass

            return True
        except Exception:
            return False

    async def delete_workspace(self, workspace_id: int | None = None) -> bool:
        if workspace_id is None:
            workspace = context.get_workspace()
            workspace_id = workspace.id if workspace else None

        if workspace_id is None:
            return False

        folder = self.settings.storage_workspace_folder
        data_prefix = f"{folder}/{workspace_id}"
        cache_prefix = f"{CACHE_PREFIX}/{folder}/{workspace_id}"
        await self.adapter.delete_directory(data_prefix)
        await self.cache_adapter.delete_directory(data_prefix)
        await self.cache_adapter.delete_directory(cache_prefix)

        return True

    async def cleanup_image_cache(self) -> int:
        """Delete cached optimized images older than cache_max_age_days, 0 or None keeping them.

        The age is the last access where the cache keeps one (filesystem), the creation elsewhere (S3): a variant
        still in use is then rebuilt on its next read. Returns the number of files deleted.
        """
        max_age = self.settings.cache_max_age_days
        if not max_age:
            return 0

        return await self.cache_adapter.delete_old_files(CACHE_PREFIX, max_age * 86400)

    async def usage(self) -> StorageUsage:
        """Count the stored files and the optimized images cache, with their bytes, in one listing when the cache
        shares the files' store."""
        data = await self.adapter.usage()
        cache_files, cache_bytes = data.pop(CACHE_PREFIX, (0, 0))

        if self.cache_adapter.location != self.adapter.location:
            cached = (await self.cache_adapter.usage(CACHE_PREFIX)).values()
            cache_files, cache_bytes = sum(f for f, _ in cached), sum(b for _, b in cached)

        return StorageUsage(
            data_files=sum(f for f, _ in data.values()),
            data_bytes=sum(b for _, b in data.values()),
            cache_files=cache_files,
            cache_bytes=cache_bytes,
        )

    # --------------------
    # Internal helpers
    # --------------------
    def _ensure_filename(self, filename: str | None, ext: str) -> str:
        if not filename:
            filename = str(uuid.uuid4()) + ".{ext}"
        return filename.replace("{ext}", ext)

    async def _finalize_store(
        self,
        *,
        file: BinaryIO,
        directory_path: str,
        filename: str | None,
        ext: str,
        mime_type: str | None,
        global_storage: bool,
        original_name: str | None,
        create_attachment: bool = False,
        attachment_values: dict[str, Any] | None = None,
    ) -> str:
        from fastedgy.storage.models.attachment import AttachmentType

        img_width, img_height, size = await to_thread.run_sync(self._inspect, file)

        safe_filename = self._ensure_filename(filename, ext)
        relative_path = f"{directory_path.strip('/')}/{safe_filename}"

        # Delete existing cache if file is being overwritten
        try:
            cache_rel = self._get_cache_path(relative_path, global_storage)
            await self.cache_adapter.delete_directory(cache_rel)
        except Exception:
            pass

        # Write via adapter
        full_path = self._resolve_path(relative_path, global_storage)
        await self.adapter.write_file(full_path, file, mime_type)

        if not create_attachment:
            return relative_path

        # Auto-create Attachment record if model is registered
        registry: Registry = get_service(Registry)

        try:
            if "Attachment" in registry.models:
                AttachmentModel: Any = registry.get_model("Attachment")
                base_name = (
                    os.path.splitext(os.path.basename(original_name))[0]
                    if original_name
                    else os.path.splitext(os.path.basename(safe_filename))[0]
                )
                values: dict[str, Any] = {
                    "type": AttachmentType.file,
                    "name": base_name,
                    "extension": ext,
                    "mime_type": mime_type or None,
                    "width": img_width,
                    "height": img_height,
                    "path": base_name,
                }
                # Caller-supplied values win over the ones derived from the file,
                # except those describing the stored bytes themselves.
                values.update(attachment_values or {})
                values.update(
                    {
                        "size_bytes": size,
                        "storage_path": relative_path,
                        "is_global": global_storage,
                    }
                )
                attachment = AttachmentModel(**values)
                await attachment.save()
        except Exception:
            # A caller that supplied values expects them applied: swallowing the
            # failure here would return a path for an attachment that does not
            # exist (or is not associated), with no way to notice. The bytes are
            # already written, so drop them rather than leave an orphan behind.
            if attachment_values:
                try:
                    await self.adapter.delete(full_path)
                except Exception:
                    logger.warning("Could not remove '%s' after a failed attachment creation", relative_path)

                raise

        return relative_path


__all__ = [
    "Storage",
]
