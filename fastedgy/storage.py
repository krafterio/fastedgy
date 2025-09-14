# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import os
import uuid
import mimetypes
import base64

from pathlib import Path

from fastapi import UploadFile

from fastedgy import context
from fastedgy.config import BaseSettings, get_service
from fastedgy.dependencies import register_service


class Storage:
    ALLOWED_EXTENSIONS = {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
    }

    def __init__(self, settings: BaseSettings):
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
    ) -> str:
        if not file.filename:
            raise ValueError("Nom de fichier manquant")

        content_type = file.content_type or ""

        if not content_type.startswith("image/"):
            raise ValueError("Seules les images sont acceptées")

        ext = os.path.splitext(file.filename)[1].lower()[1:]

        if not ext:
            raise ValueError("Extension de fichier non définie")

        if ext not in self.ALLOWED_EXTENSIONS:
            allowed_ext_str = ", ".join(self.ALLOWED_EXTENSIONS)
            raise ValueError(
                f"Extension de fichier non autorisée. Extensions acceptées: {allowed_ext_str}"
            )

        if not filename:
            filename = str(uuid.uuid4()) + ".{ext}"

        path = os.path.join(directory_path, filename.replace("{ext}", ext))
        file_path = self.get_file_path(
            path, ensure_exists=True, global_storage=global_storage
        )
        relative_path = self.get_relative_path(file_path, global_storage=global_storage)

        content = await file.read()

        with open(file_path, "wb") as f:
            f.write(content)

        return relative_path

    async def upload_from_base64(
        self,
        data: str,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
    ) -> str:
        if not data.startswith("data:"):
            raise ValueError("Le contenu n'est pas une data URL")

        header, base64_data = data.split(",", 1)
        content_type = header.split(";")[0][5:]
        ext = mimetypes.guess_extension(content_type) or ".bin"
        ext = ext.lstrip(".")

        if ext not in self.ALLOWED_EXTENSIONS:
            allowed_ext_str = ", ".join(self.ALLOWED_EXTENSIONS)
            raise ValueError(
                f"Extension de fichier non autorisée. Extensions acceptées: {allowed_ext_str}"
            )

        if not filename:
            filename = str(uuid.uuid4()) + ".{ext}"

        path = os.path.join(directory_path, filename.replace("{ext}", ext))
        file_path = self.get_file_path(
            path, ensure_exists=True, global_storage=global_storage
        )
        relative_path = self.get_relative_path(file_path, global_storage=global_storage)

        content = base64.b64decode(base64_data)

        with open(file_path, "wb") as f:
            f.write(content)

        return relative_path

    async def delete(self, file_path: str | None, global_storage: bool = False) -> bool:
        try:
            if not file_path:
                return True

            path = self.get_file_path(
                file_path, ensure_exists=False, global_storage=global_storage
            )

            if not os.path.exists(path):
                return True

            os.remove(path)

            return True
        except Exception:
            return False

    async def delete_workspace(self) -> bool:
        workspace = context.get_workspace()

        if workspace:
            return await self.delete(str(workspace.id))

        return False

    async def download_and_upload(
        self,
        file_url: str,
        directory_path: str,
        filename: str | None = None,
        global_storage: bool = False,
    ) -> str:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(file_url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    raise ValueError("L'URL ne pointe pas vers une image")

                ext_map = {
                    "image/jpeg": "jpg",
                    "image/jpg": "jpg",
                    "image/png": "png",
                    "image/gif": "gif",
                }
                ext = ext_map.get(content_type, "jpg")

                if not filename:
                    filename = str(uuid.uuid4()) + ".{ext}"

                path = os.path.join(directory_path, filename.replace("{ext}", ext))
                file_path = self.get_file_path(
                    path, ensure_exists=True, global_storage=global_storage
                )
                relative_path = self.get_relative_path(
                    file_path, global_storage=global_storage
                )

                with open(file_path, "wb") as f:
                    f.write(response.content)

                return relative_path

        except Exception as e:
            raise ValueError(f"Erreur lors du téléchargement de l'image: {str(e)}")


register_service(lambda: Storage(get_service(BaseSettings)), Storage)

__all__ = [
    "Storage",
]
