# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import mimetypes
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from pathlib import Path


from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse

from fastedgy.dependencies import Inject, get_service
from fastedgy.metadata_model.registry import MetadataModelRegistry
from starlette.responses import Response
from starlette.datastructures import UploadFile as StarletteUploadFile

from fastedgy.orm.exceptions import ObjectNotFound
from fastedgy.storage import Storage
from fastedgy.orm import Registry
from fastedgy import context
from fastedgy.schemas.storage import UploadedAttachments, UploadedModelField
from fastedgy.i18n import _t
from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import (
    PreUploadTransformer,
    PostUploadTransformer,
    PreDownloadTransformer,
    PostDownloadTransformer,
)

try:
    from uuid_extensions import uuid7  # type: ignore
except Exception:
    from uuid import uuid4 as uuid7  # type: ignore


if TYPE_CHECKING:
    from fastedgy.models.base import BaseModel
    from fastedgy.models.attachment import BaseAttachment


attachments_router = APIRouter(prefix="/storage", tags=["storage"])
manage_attachments_router = APIRouter(prefix="/storage", tags=["storage"])
router = APIRouter(prefix="/storage", tags=["storage"])
manage_router = APIRouter(prefix="/storage", tags=["storage"])


@manage_attachments_router.post(
    "/upload/attachments",
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "title": "UploadAttachments",
                        "type": "object",
                        "properties": {
                            "<filename>": {
                                "type": "string",
                                "format": "binary",
                                "description": "Key is the filename and the value is the binary content. Multiple files can be uploaded",
                            }
                        },
                        "required": ["<filename>"],
                    },
                },
            },
            "required": True,
        },
    },
)
async def upload_attachments(
    request: Request,
    storage: Storage = Inject(Storage),
    registry: Registry = Inject(Registry),
) -> UploadedAttachments:
    """Upload one or many files as Attachments."""
    # Ensure Attachment model is present for a dedicated attachment endpoint
    if "Attachment" not in registry.models:
        raise HTTPException(
            status_code=501,
            detail="Attachment model is not configured. Please add the Attachment model to your project.",
        )

    Attachment: Any = registry.get_model("Attachment")

    # Build storage directory: attachments/YYYY/MM
    now = datetime.now(context.get_timezone())
    directory_path = f"attachments/{now.strftime('%Y/%m')}"

    files = []
    results: list[Any] = []
    form = await request.form()

    for _, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            files.append(value)

    if not files:
        raise HTTPException(status_code=400, detail=_t("No files uploaded"))

    for _, file in enumerate(files):
        filename = f"{uuid7()}.{{ext}}"

        rel_path = await storage.upload(
            file=file,
            directory_path=directory_path,
            filename=filename,
            create_attachment=True,
        )

        # Fetch the created attachment
        att = await Attachment.query.filter(storage_path=rel_path).get_or_none()
        if att is None:
            raise HTTPException(
                status_code=500, detail=_t("Attachment creation failed")
            )

        results.append(att)

    return UploadedAttachments[Attachment](attachments=results)


@manage_router.post(
    "/upload/{model:str}/{model_id}/{field:str}",
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "title": "UploadModelField",
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "Binary content of the file",
                            }
                        },
                        "required": ["file"],
                    },
                },
            },
            "required": True,
        },
    },
)
async def upload_model_field_file(
    model: str,
    field: str,
    model_id: int,
    request: Request,
    storage: Storage = Inject(Storage),
) -> UploadedModelField:
    """Upload a file to a model field."""
    try:
        form = await request.form()
        file = form.get("file")

        if not file:
            raise HTTPException(status_code=400, detail=_t("File not found"))

        if not isinstance(file, StarletteUploadFile):
            raise HTTPException(
                status_code=400, detail=_t("File is not a valid upload file")
            )

        record = await _get_record(model, field, model_id)
        vtr = get_service(ViewTransformerRegistry)
        transformers_ctx: dict[str, Any] = {}
        global_storage = False

        meta_registry = get_service(MetadataModelRegistry)
        meta_model = await meta_registry.get_metadata(model)
        model_cls = await meta_registry.get_model_from_metadata(meta_model)

        for transformer in vtr.get_transformers(PreUploadTransformer, model_cls, None):
            global_storage = await transformer.pre_upload(
                request, record, field, cast(UploadFile, file), transformers_ctx
            )

        if getattr(record, field):
            await storage.delete(getattr(record, field), global_storage=global_storage)

        path = await storage.upload(
            cast(UploadFile, file),
            model,
            global_storage=global_storage,
        )
        setattr(record, field, path)
        await record.save()

        for transformer in vtr.get_transformers(PostUploadTransformer, model_cls, None):
            path = await transformer.post_upload(
                request, record, field, path, transformers_ctx
            )

        return UploadedModelField(path=path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail=_t("Model not found"))


@manage_router.delete("/file/{model:str}/{model_id}/{field:str}")
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
        raise HTTPException(status_code=404, detail=_t("Model not found"))


@attachments_router.get("/download/attachments/{id:int}")
async def download_attachment(
    id: int,
    force_download: bool = Query(False),
    w: int | None = Query(None),
    h: int | None = Query(None),
    m: str = Query("contain"),
    e: str | None = Query(None),
    storage: Storage = Inject(Storage),
    registry: Registry = Inject(Registry),
) -> Response:
    """Download an attachment by its ID.

    This endpoint retrieves an attachment record from the database,
    then streams the corresponding file from storage with the correct filename.
    """
    try:
        if "Attachment" not in registry.models:
            raise HTTPException(
                status_code=500, detail=_t("Attachment model not configured")
            )

        AttachmentModel: Any = registry.get_model("Attachment")
        record = await AttachmentModel.query.get(id=id)

        # Resolve optimized or original path (pass workspace/global flag from record if available)
        served_path, content_type = storage.get_optimized_or_original(
            record.storage_path,
            w=w,
            h=h,
            mode=m,
            out_ext=e,
            global_storage=getattr(record, "is_global", False),
        )

        if not served_path.exists():
            raise HTTPException(status_code=404, detail=_t("Attachment not found"))

        # Build filename: attachment name + ensured extension from served file
        served_ext = served_path.suffix.lstrip(".")
        filename = record.name
        if not filename.lower().endswith(f".{served_ext}"):
            filename = f"{record.name}.{served_ext}"

        async def file_stream():
            chunk_size = 1024 * 1024  # 1MB

            with open(served_path, "rb") as f:
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
            file_stream(), media_type=content_type, headers=headers
        )
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail=_t("Attachment not found"))


@router.get("/download/{path:path}")
async def download_file(
    path: str,
    request: Request,
    force_download: bool = Query(False),
    w: int | None = Query(None),
    h: int | None = Query(None),
    m: str = Query("contain"),
    e: str | None = Query(None),
    storage: Storage = Inject(Storage),
) -> Response:
    vtr = get_service(ViewTransformerRegistry)
    transformers_ctx: dict[str, Any] = {}
    global_storage = False

    for transformer in vtr.get_transformers(PreDownloadTransformer, None, None):
        global_storage = await transformer.pre_download(request, path, transformers_ctx)

    served_path, content_type = storage.get_optimized_or_original(
        path, w=w, h=h, mode=m, out_ext=e, global_storage=global_storage
    )

    if not served_path.exists():
        raise HTTPException(status_code=404, detail="Fichier non trouvé")

    for transformer in vtr.get_transformers(PostDownloadTransformer, None, None):
        served_path = await transformer.post_download(
            request, path, served_path, transformers_ctx
        )

    # Build filename based on original path but adopt served extension
    src_name = Path(path).name
    base = src_name.rsplit(".", 1)[0]
    served_ext = served_path.suffix.lstrip(".")
    filename = f"{base}.{served_ext}" if served_ext else src_name

    async def file_stream():
        chunk_size = 1024 * 1024  # 1MB

        with open(served_path, "rb") as f:
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


async def _get_record(
    model: str,
    field: str,
    model_id: int,
) -> "BaseModel":
    meta_registry = get_service(MetadataModelRegistry)

    if model == "user":
        current_user = context.get_user()

        if not current_user or current_user.id != model_id:
            raise ObjectNotFound(_t("User {model_id} not found", model_id=model_id))

        meta_model = await meta_registry.get_metadata(model)
        model_cls = await meta_registry.get_model_from_metadata(meta_model)

        if field not in model_cls.meta.fields:
            raise ValueError(
                _t("Field {field} not found in model {model}", field=field, model=model)
            )

        record = current_user
    elif model == "workspace":
        current_workspace = context.get_workspace()

        if not current_workspace or current_workspace.id != model_id:
            raise ObjectNotFound(
                _t("Workspace {model_id} not found", model_id=model_id)
            )

        meta_model = await meta_registry.get_metadata(model)
        model_cls = await meta_registry.get_model_from_metadata(meta_model)

        if field not in model_cls.meta.fields:
            raise ValueError(
                _t("Field {field} not found in model {model}", field=field, model=model)
            )

        record = current_workspace
    else:
        meta_model = await meta_registry.get_metadata(model)

        if field not in meta_model.fields:
            raise ValueError(
                _t("Field {field} not found in model {model}", field=field, model=model)
            )

        model_cls = await meta_registry.get_model_from_metadata(meta_model)
        record = await model_cls.query.get(id=model_id)

    return record


__all__ = [
    "attachments_router",
    "manage_attachments_router",
    "router",
    "manage_router",
]
