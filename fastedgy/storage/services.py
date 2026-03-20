# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import io
import uuid
import mimetypes
import base64

from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import UploadFile

from fastedgy import context
from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject, get_service
from fastedgy.i18n import _t
from fastedgy.orm import Registry
from fastedgy.storage.adapters.base import StorageAdapter
from fastedgy.storage.adapters.filesystem import FilesystemAdapter

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - Pillow optional at runtime
    Image = None  # type: ignore


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
        )

    # Default: filesystem
    return FilesystemAdapter(root=settings.storage_data_path)


class Storage:
    def __init__(self, settings: BaseSettings = Inject(BaseSettings)):
        self.settings = settings
        self.adapter: StorageAdapter = _create_adapter(
            settings, settings.storage_adapter
        )
        self.cache_adapter: FilesystemAdapter = FilesystemAdapter(
            root=settings.storage_data_path
        )
        if settings.storage_cache_adapter != "filesystem":
            self.cache_adapter = _create_adapter(
                settings, settings.storage_cache_adapter
            )

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
        clean = path.strip("/")
        if prefix:
            return f"{prefix}/{clean}" if clean else prefix
        return clean

    # Backward-compatible path methods (filesystem only)
    def get_base_path(self, global_storage: bool = False) -> Path:
        workspace = context.get_workspace()
        if workspace and not global_storage:
            sub = os.path.join(
                self.settings.storage_workspace_folder, str(workspace.id)
            )
        else:
            sub = "global"

        return Path(os.path.join(self.settings.storage_data_path, sub))

    def get_directory_path(
        self, path: str, ensure_exists: bool = True, global_storage: bool = False
    ) -> Path:
        dir_path = self.get_base_path(global_storage)

        safe_custom_path = Path(path.strip("/")).parts
        dir_path = dir_path.joinpath(*safe_custom_path)

        if ensure_exists:
            os.makedirs(dir_path, exist_ok=True)

        return dir_path

    def get_file_path(
        self, path: str, ensure_exists: bool = True, global_storage: bool = False
    ) -> Path:
        path_parts = Path(path.strip("/")).parts
        directory_path = ""
        filename = path

        if len(path_parts) > 0:
            filename = path_parts[-1]
            directory_parts = path_parts[:-1]

            if directory_parts:
                directory_path = "/".join(directory_parts)

        directory_path = self.get_directory_path(
            directory_path, ensure_exists, global_storage
        )

        return directory_path.joinpath(filename)

    def get_relative_path(self, file_path: Path, global_storage: bool = False) -> str:
        data_path = self.get_base_path(global_storage)

        return str(file_path.relative_to(data_path))

    # --------------------
    # Adapter-based file operations
    # --------------------
    async def file_exists(
        self, relative_path: str, global_storage: bool = False
    ) -> bool:
        """Check if a file exists in storage."""
        full_path = self._resolve_path(relative_path, global_storage)
        return await self.adapter.exists(full_path)

    async def file_size(self, relative_path: str, global_storage: bool = False) -> int:
        """Get the size of a file in storage."""
        full_path = self._resolve_path(relative_path, global_storage)
        return await self.adapter.file_size(full_path)

    async def read_file(
        self, relative_path: str, global_storage: bool = False
    ) -> bytes:
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

    def _get_cache_path(self, path: str, global_storage: bool = False) -> str:
        """Return the cache-relative path for a given path."""
        workspace = context.get_workspace()
        clean = path.strip("/")
        if workspace and not global_storage:
            folder = self.settings.storage_workspace_folder
            return f"cache_optimized_images/{folder}/{workspace.id}/{clean}"
        return f"cache_optimized_images/global/{clean}"

    def _is_image_path(self, path: str) -> bool:
        name = path.rsplit("/", 1)[-1] if "/" in path else path
        mime = mimetypes.guess_type(name)[0]
        return bool(mime and mime.startswith("image/"))

    def _clamp_dimensions(
        self, ow: int, oh: int, w: int | None, h: int | None
    ) -> tuple[int | None, int | None]:
        cw = None if w is None else min(w, ow)
        ch = None if h is None else min(h, oh)
        return cw, ch

    def _compute_target_size(
        self, ow: int, oh: int, w: int | None, h: int | None, mode: str
    ) -> tuple[int, int, str]:
        if w and not h:
            scale = w / ow
            th = int(round(oh * scale))
            return w, max(1, th), "contain"
        if h and not w:
            scale = h / oh
            tw = int(round(ow * scale))
            return max(1, tw), h, "contain"

        if not w or not h:
            return ow, oh, "contain"

        mode = "cover" if str(mode).lower() == "cover" else "contain"
        if mode == "contain":
            scale = min(w / ow, h / oh)
            tw = int(round(ow * scale))
            th = int(round(oh * scale))
            return max(1, tw), max(1, th), mode
        else:
            scale = max(w / ow, h / oh)
            tw = int(round(ow * scale))
            th = int(round(oh * scale))
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
        img: "Image.Image",  # type: ignore[name-defined]
        pil_format: str,
        quality: int,
    ) -> bytes:
        save_kwargs: dict[str, Any] = {}
        if pil_format == "JPEG":
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            save_kwargs.update(
                {"optimize": True, "quality": quality, "progressive": True}
            )
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
    ) -> tuple[str, bytes, str]:
        """Generate optimized image and save to cache.

        Returns (cache_path, image_bytes, mime_type).
        If no optimization needed, returns original data.
        """
        if Image is None:
            mime = mimetypes.guess_type(source_name)[0] or "application/octet-stream"
            return cache_path, source_data, mime

        with Image.open(io.BytesIO(source_data)) as img:  # type: ignore[attr-defined]
            ow, oh = img.size
            w, h = self._clamp_dimensions(ow, oh, w, h)
            tw, th, mode = self._compute_target_size(ow, oh, w, h, mode)

            src_ext = (
                source_name.rsplit(".", 1)[-1].lower() if "." in source_name else ""
            )
            out_format, mime_type = self._format_from_ext(out_ext, src_ext)

            if (tw, th) == (ow, oh) and out_format.lower() == src_ext.lower():
                mime = mimetypes.guess_type(source_name)[0] or mime_type
                return cache_path, source_data, mime

            if mode == "contain":
                resized = img.resize((tw, th), Image.LANCZOS)  # type: ignore
                final_img = resized
            else:
                resized = img.resize((tw, th), Image.LANCZOS)  # type: ignore
                cw = w or tw
                ch = h or th
                left = max(0, (tw - cw) // 2)
                top = max(0, (th - ch) // 2)
                right = left + cw
                bottom = top + ch
                final_img = resized.crop((left, top, right, bottom))

            quality = self._get_image_quality()
            data = self._save_image_to_bytes(final_img, out_format, quality)

            # Save to cache adapter
            await self.cache_adapter.write(cache_path, data, mime_type)

            return cache_path, data, mime_type

    async def get_optimized_or_original(
        self,
        source_relative_path: str,
        *,
        w: int | None = None,
        h: int | None = None,
        mode: str = "contain",
        out_ext: str | None = None,
        global_storage: bool = False,
    ) -> tuple[str, str]:
        """Return (relative_path, mime_type) for serving.

        The returned path is either the original or a cached optimized version.
        Use stream_download() to actually stream the content.
        """
        source_name = (
            source_relative_path.rsplit("/", 1)[-1]
            if "/" in source_relative_path
            else source_relative_path
        )
        full_source = self._resolve_path(source_relative_path, global_storage)

        if not await self.adapter.exists(full_source):
            mime = mimetypes.guess_type(source_name)[0] or "application/octet-stream"
            return source_relative_path, mime

        is_image = self._is_image_path(source_relative_path)
        options_provided = any([w, h, out_ext, (mode and mode != "contain")])

        if (not is_image) or (not options_provided):
            mime = mimetypes.guess_type(source_name)[0] or "application/octet-stream"
            return source_relative_path, mime

        # Compute cache path
        req_w = 0 if w is None else w
        req_h = 0 if h is None else h
        mode_name = "cover" if str(mode).lower() == "cover" else "contain"

        src_ext = source_name.rsplit(".", 1)[-1].lower() if "." in source_name else ""
        out_fmt, mime_type = self._format_from_ext(out_ext, src_ext)
        out_ext_final = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(
            out_fmt, "jpg"
        )

        cache_rel = self._get_cache_path(source_relative_path, global_storage)
        cache_path = f"{cache_rel}/{mode_name}_w{req_w}_h{req_h}.{out_ext_final}"

        # Check cache
        if await self.cache_adapter.exists(cache_path):
            await self.cache_adapter.touch(cache_path)
            return f"__cache__:{cache_path}", mime_type

        # Read source from adapter, generate cache
        source_data = await self.adapter.read(full_source)
        cache_path, _, mime_type = await self._generate_cache_image(
            source_data,
            source_name,
            cache_path,
            w=w,
            h=h,
            mode=mode,
            out_ext=out_ext if out_ext else src_ext,
        )

        return f"__cache__:{cache_path}", mime_type

    async def stream_download(
        self,
        resolved_path: str,
        global_storage: bool = False,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[bytes]:
        """Stream a file for download based on the path from get_optimized_or_original.

        Handles both cached images (via cache_adapter) and original files (via adapter).
        """
        if resolved_path.startswith("__cache__:"):
            cache_path = resolved_path[len("__cache__:") :]
            async for chunk in self.cache_adapter.read_stream(cache_path, chunk_size):
                yield chunk
        else:
            full_path = self._resolve_path(resolved_path, global_storage)
            async for chunk in self.adapter.read_stream(full_path, chunk_size):
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
        if resolved_path.startswith("__cache__:"):
            cache_path = resolved_path[len("__cache__:") :]
            async for chunk in self.cache_adapter.read_range_stream(
                cache_path, start, end, chunk_size
            ):
                yield chunk
        else:
            full_path = self._resolve_path(resolved_path, global_storage)
            async for chunk in self.adapter.read_range_stream(
                full_path, start, end, chunk_size
            ):
                yield chunk

    async def get_file_size_for_download(
        self,
        resolved_path: str,
        global_storage: bool = False,
    ) -> int:
        """Get file size for a resolved path (from get_optimized_or_original)."""
        if resolved_path.startswith("__cache__:"):
            cache_path = resolved_path[len("__cache__:") :]
            return await self.cache_adapter.file_size(cache_path)
        else:
            full_path = self._resolve_path(resolved_path, global_storage)
            return await self.adapter.file_size(full_path)

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
    ) -> str:
        if not file.filename:
            raise ValueError("Missing filename")

        ext = os.path.splitext(file.filename)[1].lower()[1:]
        if not ext:
            guessed = mimetypes.guess_extension(file.content_type or "") or ".bin"
            ext = guessed.lstrip(".")

        content = await file.read()
        return await self._finalize_store(
            content=content,
            directory_path=directory_path,
            filename=filename,
            ext=ext,
            mime_type=file.content_type or None,
            global_storage=global_storage,
            original_name=file.filename,
            create_attachment=create_attachment,
        )

    async def upload_from_base64(
        self,
        data: str,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
    ) -> str:
        if not data.startswith("data:"):
            raise ValueError("Content is not a data URL")

        header, base64_data = data.split(",", 1)
        content_type = header.split(";")[0][5:]
        ext = mimetypes.guess_extension(content_type) or ".bin"
        ext = ext.lstrip(".")

        content = base64.b64decode(base64_data)

        return await self._finalize_store(
            content=content,
            directory_path=directory_path,
            filename=filename,
            ext=ext,
            mime_type=content_type or None,
            global_storage=global_storage,
            original_name=filename.replace("{ext}", ext) if filename else None,
            create_attachment=create_attachment,
        )

    async def download_and_upload(
        self,
        file_url: str,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
    ) -> str:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(file_url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                guessed = mimetypes.guess_extension(content_type) or ".bin"
                ext = guessed.lstrip(".")

                content = response.content

                return await self._finalize_store(
                    content=content,
                    directory_path=directory_path,
                    filename=filename,
                    ext=ext,
                    mime_type=content_type or None,
                    global_storage=global_storage,
                    original_name=filename.replace("{ext}", ext) if filename else None,
                    create_attachment=create_attachment,
                )
        except Exception as e:
            raise ValueError(
                _t("Error while downloading the file: {error}", error=str(e))
            )

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

    async def delete_workspace(self) -> bool:
        workspace = context.get_workspace()

        if workspace:
            folder = self.settings.storage_workspace_folder
            data_prefix = f"{folder}/{workspace.id}"
            cache_prefix = f"cache_optimized_images/{folder}/{workspace.id}"
            await self.adapter.delete_directory(data_prefix)
            await self.cache_adapter.delete_directory(data_prefix)
            await self.cache_adapter.delete_directory(cache_prefix)
            return True

        return False

    async def cleanup_image_cache(self) -> int:
        """Delete cached optimized images older than cache_max_age_days.

        Returns the number of files deleted.
        """
        max_age = self.settings.cache_max_age_days
        if max_age is None:
            return 0

        return await self.cache_adapter.delete_old_files(
            "cache_optimized_images", max_age * 86400
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
        content: bytes,
        directory_path: str,
        filename: str | None,
        ext: str,
        mime_type: str | None,
        global_storage: bool,
        original_name: str | None,
        create_attachment: bool = False,
    ) -> str:
        from fastedgy.storage.models.attachment import AttachmentType

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
        await self.adapter.write(full_path, content, mime_type)

        if not create_attachment:
            return relative_path

        # Auto-create Attachment record if model is registered
        registry: Registry = get_service(Registry)

        try:
            if "Attachment" in registry.models:
                AttachmentModel: Any = registry.get_model("Attachment")
                img_width: int | None = None
                img_height: int | None = None
                if (mime_type or "").startswith("image/"):
                    try:
                        from PIL import Image  # type: ignore

                        with Image.open(io.BytesIO(content)) as img:  # type: ignore
                            img_width, img_height = img.size
                    except Exception:
                        pass
                base_name = (
                    os.path.splitext(os.path.basename(original_name))[0]
                    if original_name
                    else os.path.splitext(os.path.basename(safe_filename))[0]
                )
                attachment = AttachmentModel(  # type: ignore[misc]
                    type=AttachmentType.file,
                    name=base_name,
                    extension=ext,
                    mime_type=mime_type or None,
                    size_bytes=len(content),
                    width=img_width,
                    height=img_height,
                    storage_path=relative_path,
                    is_global=global_storage,
                    path=base_name,
                )
                await attachment.save()
        except Exception:
            pass

        return relative_path


__all__ = [
    "Storage",
]
