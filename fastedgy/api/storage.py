# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import mimetypes
import re as _re
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from pathlib import Path
from urllib.parse import quote


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
    PostDeleteFileTransformer,
    PreDeleteFileTransformer,
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

_RANGE_RE = _re.compile(r"bytes=(\d+)-(\d*)")

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
    request: Request,
    model: str,
    field: str,
    model_id: int,
    storage: Storage = Inject(Storage),
) -> None:
    try:
        record = await _get_record(model, field, model_id)
        meta_registry = get_service(MetadataModelRegistry)
        meta_model = await meta_registry.get_metadata(model)
        model_cls = await meta_registry.get_model_from_metadata(meta_model)
        vtr = get_service(ViewTransformerRegistry)
        transformers_ctx: dict[str, Any] = {}
        global_storage = False

        for transformer in vtr.get_transformers(
            PreDeleteFileTransformer, model_cls, None
        ):
            global_storage = await transformer.pre_delete_file(
                request, model, model_id, field, record, transformers_ctx
            )

        if getattr(record, field):
            await storage.delete(getattr(record, field), global_storage=global_storage)

        setattr(record, field, None)
        await record.save()

        for transformer in vtr.get_transformers(
            PostDeleteFileTransformer, model_cls, None
        ):
            await transformer.post_delete_file(
                request, model, model_id, field, record, transformers_ctx
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail=_t("Model not found"))


def _build_download_headers(
    filename: str, force_download: bool = False
) -> dict[str, str]:
    ascii_filename = filename.encode("ascii", "ignore").decode("ascii") or "download"
    encoded_filename = quote(filename, safe="")
    content_disposition = "attachment" if force_download else "inline"

    return {
        "Content-Disposition": (
            f"{content_disposition}; "
            f'filename="{ascii_filename}"; '
            f"filename*=UTF-8''{encoded_filename}"
        ),
    }


def _parse_range(range_header: str | None, total_size: int) -> tuple[int, int] | None:
    """Parse a Range header and return (start, end) inclusive, or None."""
    if not range_header:
        return None
    match = _RANGE_RE.match(range_header)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else total_size - 1
    end = min(end, total_size - 1)
    if start > end or start >= total_size:
        return None
    return start, end


async def _serve_download(
    request: Request,
    storage: Storage,
    resolved_path: str,
    content_type: str,
    filename: str,
    force_download: bool,
    global_storage: bool,
) -> Response:
    """Serve a file download with Range request support."""
    total_size = await storage.get_file_size_for_download(
        resolved_path, global_storage=global_storage
    )

    range_header = request.headers.get("range")
    byte_range = _parse_range(range_header, total_size)

    headers = _build_download_headers(filename, force_download)
    headers["Accept-Ranges"] = "bytes"

    if byte_range:
        start, end = byte_range
        content_length = end - start + 1
        headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
        headers["Content-Length"] = str(content_length)

        return StreamingResponse(
            storage.stream_range_download(
                resolved_path,
                start,
                end,
                global_storage=global_storage,
            ),
            status_code=206,
            media_type=content_type,
            headers=headers,
        )

    headers["Content-Length"] = str(total_size)

    return StreamingResponse(
        storage.stream_download(resolved_path, global_storage=global_storage),
        media_type=content_type,
        headers=headers,
    )


@attachments_router.get("/download/attachments/{id:int}")
async def download_attachment(
    id: int,
    request: Request,
    force_download: bool = Query(False),
    w: int | None = Query(None),
    h: int | None = Query(None),
    m: str = Query("contain"),
    e: str | None = Query(None),
    storage: Storage = Inject(Storage),
    registry: Registry = Inject(Registry),
) -> Response:
    """Download an attachment by its ID."""
    try:
        if "Attachment" not in registry.models:
            raise HTTPException(
                status_code=500, detail=_t("Attachment model not configured")
            )

        AttachmentModel: Any = registry.get_model("Attachment")
        record = await AttachmentModel.query.get(id=id)

        global_storage = getattr(record, "is_global", False)

        resolved_path, content_type = await storage.get_optimized_or_original(
            record.storage_path,
            w=w,
            h=h,
            mode=m,
            out_ext=e,
            global_storage=global_storage,
        )

        # Check file exists
        if not resolved_path.startswith("__cache__:"):
            if not await storage.file_exists(
                resolved_path, global_storage=global_storage
            ):
                raise HTTPException(status_code=404, detail=_t("Attachment not found"))

        # Build filename
        served_ext = resolved_path.rsplit(".", 1)[-1] if "." in resolved_path else ""
        filename = record.name
        if served_ext and not filename.lower().endswith(f".{served_ext}"):
            filename = f"{record.name}.{served_ext}"

        return await _serve_download(
            request,
            storage,
            resolved_path,
            content_type,
            filename,
            force_download,
            global_storage,
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

    resolved_path, content_type = await storage.get_optimized_or_original(
        path, w=w, h=h, mode=m, out_ext=e, global_storage=global_storage
    )

    # Check file exists
    if not resolved_path.startswith("__cache__:"):
        if not await storage.file_exists(resolved_path, global_storage=global_storage):
            raise HTTPException(status_code=404, detail="Fichier non trouvé")

    for transformer in vtr.get_transformers(PostDownloadTransformer, None, None):
        resolved_path = await transformer.post_download(
            request, path, resolved_path, transformers_ctx
        )

    # Build filename
    src_name = Path(path).name
    base = src_name.rsplit(".", 1)[0]
    served_ext = resolved_path.rsplit(".", 1)[-1] if "." in resolved_path else ""
    filename = f"{base}.{served_ext}" if served_ext else src_name

    return await _serve_download(
        request,
        storage,
        resolved_path,
        content_type,
        filename,
        force_download,
        global_storage,
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
