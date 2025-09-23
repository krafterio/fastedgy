# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import io
import uuid
import mimetypes
import base64
import shutil

from pathlib import Path
from typing import Any

from fastapi import UploadFile

from fastedgy import context
from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject, get_service
from fastedgy.i18n import _t
from fastedgy.orm import Registry

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - Pillow optional at runtime
    Image = None  # type: ignore


class Storage:
    def __init__(self, settings: BaseSettings = Inject(BaseSettings)):
        self.settings = settings

    def get_base_path(self, global_storage: bool = False) -> Path:
        workspace = context.get_workspace()
        workspace_id = str(workspace.id) if workspace and not global_storage else ""

        return Path(os.path.join(self.settings.storage_data_path, workspace_id))

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
    # Image optimization
    # --------------------
    def _get_image_quality(self) -> int:
        """Return image quality from settings, defaulting to 80.

        Uses settings.image_quality when available.
        """
        try:
            q = int(getattr(self.settings, "image_quality", 80))
        except Exception:
            q = 80
        return max(1, min(100, q))

    def _get_cache_root(self, global_storage: bool = False) -> Path:
        return self.get_directory_path(
            "cache_optimized_images", ensure_exists=True, global_storage=global_storage
        )

    def _get_image_cache_dir_for(
        self, source_relative_path: str, global_storage: bool = False
    ) -> Path:
        """Return the cache directory for a given source relative path.

        Example: attachments/2025/09/abc.webp → cache_optimized_images/attachments/2025/09/abc.webp/
        """
        safe_rel_parts = Path(source_relative_path.strip("/")).parts
        cache_root = self._get_cache_root(global_storage=global_storage)
        cache_dir = cache_root.joinpath(*safe_rel_parts)
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _is_image_path(self, path: Path) -> bool:
        mime = mimetypes.guess_type(path.name)[0]
        return bool(mime and mime.startswith("image/"))

    def _clamp_dimensions(
        self, ow: int, oh: int, w: int | None, h: int | None
    ) -> tuple[int | None, int | None]:
        """Clamp requested dimensions to not exceed original while preserving None."""
        cw = None if w is None else min(w, ow)
        ch = None if h is None else min(h, oh)
        return cw, ch

    def _compute_target_size(
        self, ow: int, oh: int, w: int | None, h: int | None, mode: str
    ) -> tuple[int, int, str]:
        """Compute final width/height and actual fit mode used.

        - If only one of w/h provided, maintain aspect ratio (no crop).
        - If both provided:
          - contain: fit inside w x h (no crop)
          - cover: fill w x h then center-crop
        Returns (tw, th, mode) where mode is 'contain' or 'cover' actually used.
        """
        # When only one side provided → aspect-preserving resize
        if w and not h:
            scale = w / ow
            th = int(round(oh * scale))
            return w, max(1, th), "contain"
        if h and not w:
            scale = h / oh
            tw = int(round(ow * scale))
            return max(1, tw), h, "contain"

        if not w or not h:
            # Neither provided: return original
            return ow, oh, "contain"

        mode = "cover" if str(mode).lower() == "cover" else "contain"
        if mode == "contain":
            scale = min(w / ow, h / oh)
            tw = int(round(ow * scale))
            th = int(round(oh * scale))
            return max(1, tw), max(1, th), mode
        else:
            # cover: scale to cover then we'll crop later
            scale = max(w / ow, h / oh)
            tw = int(round(ow * scale))
            th = int(round(oh * scale))
            return max(1, tw), max(1, th), mode

    def _format_from_ext(self, ext: str | None, fallback: str) -> tuple[str, str]:
        """Return (pil_format, mime_type) from extension.

        ext must be like 'jpg'|'png'|'webp'. Fallback is extension inferred from source.
        """
        e = (ext or fallback or "").lower().lstrip(".")
        if e in ("jpg", "jpeg"):
            return "JPEG", "image/jpeg"
        if e == "png":
            return "PNG", "image/png"
        if e == "webp":
            return "WEBP", "image/webp"
        # default to original fallback if unknown
        if fallback in ("jpg", "jpeg"):
            return "JPEG", "image/jpeg"
        if fallback == "png":
            return "PNG", "image/png"
        if fallback == "webp":
            return "WEBP", "image/webp"
        return "JPEG", "image/jpeg"

    def _save_image(
        self, img: "Image.Image", dest: Path, pil_format: str, quality: int
    ) -> None:  # type: ignore[name-defined]
        save_kwargs: dict[str, Any] = {}
        if pil_format == "JPEG":
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            save_kwargs.update(
                {"optimize": True, "quality": quality, "progressive": True}
            )
        elif pil_format == "PNG":
            # compress_level 0..9 (inverse of quality). Map roughly.
            compress_level = max(0, min(9, round((100 - quality) * 9 / 100)))
            save_kwargs.update({"optimize": True, "compress_level": compress_level})
        elif pil_format == "WEBP":
            save_kwargs.update({"quality": quality, "method": 4})
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, pil_format, **save_kwargs)

    def _generate_cache_image(
        self,
        source_path: Path,
        cache_path: Path,
        *,
        w: int | None,
        h: int | None,
        mode: str,
        out_ext: str | None,
    ) -> tuple[Path, str]:
        """Generate optimized image in cache and return (cache_path, mime_type)."""
        if Image is None:
            # Pillow not available → no optimization
            return source_path, mimetypes.guess_type(source_path.name)[
                0
            ] or "application/octet-stream"

        with Image.open(source_path) as img:  # type: ignore[attr-defined]
            ow, oh = img.size
            # Clamp dimensions so we never upscale beyond original
            w, h = self._clamp_dimensions(ow, oh, w, h)
            tw, th, mode = self._compute_target_size(ow, oh, w, h, mode)

            # If requested dimensions are equal to original and no format change, return original
            src_ext = source_path.suffix.lower().lstrip(".")
            out_format, mime_type = self._format_from_ext(out_ext, src_ext)

            if (tw, th) == (ow, oh) and out_format.lower() == src_ext.lower():
                return source_path, mimetypes.guess_type(source_path.name)[
                    0
                ] or mime_type

            # Resize
            if mode == "contain" or not (w and h):
                resized = img.resize((tw, th), Image.LANCZOS)
                final_img = resized
            else:
                # cover: first resize to (tw, th), then center-crop to requested (w, h)
                resized = img.resize((tw, th), Image.LANCZOS)
                # target crop size is the requested (w, h) clamped
                cw = w or tw
                ch = h or th
                left = max(0, (tw - cw) // 2)
                top = max(0, (th - ch) // 2)
                right = left + cw
                bottom = top + ch
                final_img = resized.crop((left, top, right, bottom))

            quality = self._get_image_quality()
            self._save_image(final_img, cache_path, out_format, quality)
            return cache_path, mime_type

    def get_optimized_or_original(
        self,
        source_relative_path: str,
        *,
        w: int | None = None,
        h: int | None = None,
        mode: str = "contain",
        out_ext: str | None = None,
        global_storage: bool = False,
    ) -> tuple[Path, str]:
        """Return a path to an optimized (or original) file and its MIME type.

        - If the source is not an image or no optimization requested, returns original.
        - Otherwise, returns cached optimized image, generating it when missing.
        """
        # Resolve source absolute path
        source_path = self.get_file_path(
            source_relative_path, ensure_exists=False, global_storage=global_storage
        )
        if not source_path.exists():
            return source_path, mimetypes.guess_type(source_path.name)[
                0
            ] or "application/octet-stream"

        # Quick exit if not an image or no options provided
        is_image = self._is_image_path(source_path)
        options_provided = any([w, h, out_ext, (mode and mode != "contain")])
        if (not is_image) or (not options_provided):
            return source_path, mimetypes.guess_type(source_path.name)[
                0
            ] or "application/octet-stream"

        # Compute cache file name from final requested parameters (use 0 when None for name stability)
        # We'll still compute actual dimensions in generator; name records requested box.
        req_w = 0 if w is None else w
        req_h = 0 if h is None else h
        mode_name = "cover" if str(mode).lower() == "cover" and (w and h) else "contain"

        cache_dir = self._get_image_cache_dir_for(
            source_relative_path, global_storage=global_storage
        )
        # Determine extension to write
        src_ext = source_path.suffix.lower().lstrip(".")
        out_fmt, mime_type = self._format_from_ext(out_ext, src_ext)
        out_ext_final = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(
            out_fmt, "jpg"
        )
        cache_name = f"{mode_name}_w{req_w}_h{req_h}.{out_ext_final}"
        cache_path = cache_dir.joinpath(cache_name)

        if cache_path.exists():
            return cache_path, mime_type

        # Generate and save cache
        return self._generate_cache_image(
            source_path,
            cache_path,
            w=w,
            h=h,
            mode=mode,
            out_ext=out_ext if out_ext else src_ext,
        )

    async def upload(
        self,
        file: UploadFile,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
        create_attachment: bool = False,
    ) -> str:
        """Upload any file type and optionally auto-register an Attachment model.

        Behavior:
        - Always writes the file to storage using a generated filename if not provided.
        - If the "Attachment" model exists in the Registry, also creates a corresponding
          Attachment record (type "file"). Otherwise, only the file is written.

        Returns the relative storage path.
        """
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
        """Upload a file from a data URL and optionally create an Attachment record.

        Accepts any data URL content type.
        """
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
        """Download a remote file and store it locally, optionally creating Attachment.

        Accepts any content type returned by the server.
        """
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
            raise ValueError(f"Error while downloading the file: {str(e)}")

    async def delete(
        self,
        file_path: str | None,
        global_storage: bool = False,
        delete_record: bool = False,
    ) -> bool:
        """Delete an Attachment record (if configured) and then remove the file.

        Always returns True on success, False on unexpected exceptions.
        """
        try:
            if not file_path:
                return True

            # If Attachment model exists, delete records first
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
                # Ignore model-related failures and proceed with file removal
                pass

            # Remove the file itself
            path = self.get_file_path(
                file_path, ensure_exists=False, global_storage=global_storage
            )
            if os.path.exists(path):
                os.remove(path)

            # Remove optimized cache directory for this file (best-effort)
            try:
                cache_dir = self._get_image_cache_dir_for(
                    file_path, global_storage=global_storage
                )
                shutil.rmtree(cache_dir, ignore_errors=True)
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def delete_workspace(self) -> bool:
        workspace = context.get_workspace()

        if workspace:
            return await self.delete(str(workspace.id))

        return False

    def _ensure_filename(self, filename: str | None, ext: str) -> str:
        """Return a usable filename template, generating one when missing.

        Replaces the {ext} placeholder with the provided extension.
        """
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
        """Write file to storage and optionally create an Attachment record.

        Returns the relative storage path.
        """
        from fastedgy.storage.models.attachment import AttachmentType

        safe_filename = self._ensure_filename(filename, ext)
        path = os.path.join(directory_path, safe_filename)
        file_path = self.get_file_path(
            path, ensure_exists=True, global_storage=global_storage
        )
        relative_path = self.get_relative_path(file_path, global_storage=global_storage)

        with open(file_path, "wb") as f:
            f.write(content)

        if not create_attachment:
            return relative_path

        # Auto-create Attachment record if model is registered
        registry: Registry = get_service(Registry)

        try:
            if "Attachment" in registry.models:
                AttachmentModel: Any = registry.get_model("Attachment")
                # Try to extract image dimensions when applicable
                img_width: int | None = None
                img_height: int | None = None
                if (mime_type or "").startswith("image/"):
                    try:
                        from PIL import Image  # type: ignore

                        with Image.open(io.BytesIO(content)) as img:  # type: ignore
                            img_width, img_height = img.size
                    except Exception:
                        # Pillow unsupported image -> ignore
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
            # Never fail the upload if attachment creation fails
            pass

        return relative_path


__all__ = [
    "Storage",
]
