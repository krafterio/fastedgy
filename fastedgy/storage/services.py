# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import io
import uuid
import mimetypes
import base64

from pathlib import Path
from typing import Any

from fastapi import UploadFile

from fastedgy import context
from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject, get_service
from fastedgy.i18n import _t
from fastedgy.orm import Registry


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
