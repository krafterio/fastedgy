# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import mimetypes
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse

from fastedgy.dependencies import Inject, get_service
from fastedgy.metadata_model.registry import MetadataModelRegistry
from starlette.responses import Response

from fastedgy.orm.exceptions import ObjectNotFound
from fastedgy.storage import Storage
from fastedgy import context

if TYPE_CHECKING:
    from fastedgy.models.base import BaseModel


router = APIRouter(prefix="/storage", tags=["storage"])


@router.post("/upload/{model:str}/{model_id}/{field:str}")
async def upload_file(
    model: str,
    field: str,
    model_id: int,
    file: UploadFile = File(...),
    storage: Storage = Inject(Storage),
) -> str:
    try:
        record = await _get_record(model, field, model_id)

        if getattr(record, field):
            await storage.delete(getattr(record, field))

        path = await storage.upload(file, model)
        setattr(record, field, path)
        await record.save()

        return path
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="Model not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Error uploading file")


@router.delete("/file/{model:str}/{model_id}/{field:str}")
async def delete_file(
    model: str,
    field: str,
    model_id: int,
    storage: Storage = Inject(Storage),
) -> None:
    try:
        record = await _get_record(model, field, model_id)

        if getattr(record, field):
            await storage.delete(getattr(record, field))

        setattr(record, field, None)
        await record.save()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="Model not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Error deleteing file")


@router.get("/download/{path:path}")
async def download_file(
    path: str,
    force_download: bool = Query(False),
    storage: Storage = Inject(Storage),
) -> Response:
    try:
        file_path = storage.get_file_path(path, ensure_exists=False)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Fichier non trouvé")

        filename = file_path.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        async def file_stream():
            chunk_size = 1024 * 1024  # 1MB

            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk

        headers = {
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
                if force_download
                else f'inline; filename="{filename}"'
            ),
        }

        return StreamingResponse(
            file_stream(),
            media_type=content_type,
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erreur lors du téléchargement: {str(e)}"
        )


async def _get_record(
    model: str,
    field: str,
    model_id: int,
) -> "BaseModel":
    meta_registry = get_service(MetadataModelRegistry)

    if model == "user":
        current_user = context.get_user()

        if not current_user or current_user.id != model_id:
            raise ObjectNotFound(f"User {model_id} not found")

        meta_model = await meta_registry.get_metadata(model)
        model_cls = await meta_registry.get_model_from_metadata(meta_model)

        if field not in model_cls.meta.fields:
            raise ValueError(f"Field {field} not found in model {model}")

        record = current_user
    elif model == "workspace":
        current_workspace = context.get_workspace()

        if not current_workspace or current_workspace.id != model_id:
            raise ObjectNotFound(f"Workspace {model_id} not found")

        meta_model = await meta_registry.get_metadata(model)
        model_cls = await meta_registry.get_model_from_metadata(meta_model)

        if field not in model_cls.meta.fields:
            raise ValueError(f"Field {field} not found in model {model}")

        record = current_workspace
    else:
        meta_model = await meta_registry.get_metadata(model)

        if field not in meta_model.fields:
            raise ValueError(f"Field {field} not found in model {model}")

        model_cls = await meta_registry.get_model_from_metadata(meta_model)
        record = await model_cls.query.get(id=model_id)

    return record
