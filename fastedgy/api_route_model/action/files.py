# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""The writes of a file field, the same whichever way they come: the storage routes (upload, delete) or a create or
a patch of the API (a data URL, a null). Both run begin_file_writes before the record is written, end_file_writes
once it is, and discard_file_writes when it is not. The files they let go are removed by schedule_file_cleanup."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from fastapi import HTTPException, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile

from fastedgy.api_route_model.registry import ViewTransformerRegistry
from fastedgy.api_route_model.view_transformer import (
    BaseViewTransformer,
    PostDeleteFileTransformer,
    PostUploadTransformer,
    PreDeleteFileTransformer,
    PreUploadTransformer,
)
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.metadata_model.generator import generate_metadata_name
from fastedgy.orm.fields import FileField, stored_image_of
from fastedgy.storage import Storage, data_url_upload
from fastedgy.storage.cleanup import schedule_file_cleanup
from fastedgy.storage.routing import is_global_storage_model

type FileUploads = dict[str, StarletteUploadFile | None]


@dataclass(frozen=True)
class FileWrite:
    """The write of one file field: the path it held, the path stored for it (None for a removal), and whether its
    files lie in the global storage."""

    previous: str | None
    path: str | None
    global_storage: bool


type FileWrites = dict[str, FileWrite]


def take_file_writes(model_cls: Any, values: dict[str, Any], record: Any = None) -> FileUploads:
    """Pop from ``values`` the file writes they hold: a data URL written to a file field, as the upload it holds, and
    a null written over the file ``record`` holds, as its removal. Any other value of a file field, a path, stays a
    plain write."""
    uploads: FileUploads = {}

    for name, value in list(values.items()):
        if not isinstance(model_cls.meta.fields.get(name), FileField):
            continue

        if isinstance(value, str) and value.startswith("data:"):
            uploads[name] = data_url_upload(values.pop(name))
        elif value is None and record is not None and getattr(record, name, None):
            uploads[name] = values.pop(name)

    return uploads


async def begin_file_writes(
    request: Request,
    model_cls: Any,
    record: Any,
    uploads: FileUploads,
    ctx: dict[str, Any],
    transformers: list[type[BaseViewTransformer]] | None = None,
    authorize: Callable[[dict[str, Any]], None] | None = None,
) -> FileWrites:
    """Write the file fields of ``record`` before it is saved: an upload is optimized when its field is an
    ImageField, handed to the pre-upload transformers, which see what will be stored, then stored in the directory
    named after the model (its metadata name). A None removes the file, through the pre-delete-file transformers. ``authorize`` runs
    after the transformers, before anything is stored. Nothing stays stored when one of them is refused."""
    storage = get_service(Storage)
    vtr = get_service(ViewTransformerRegistry)
    writes: FileWrites = {}

    try:
        for field, file in uploads.items():
            previous = getattr(record, field, None)
            global_storage = is_global_storage_model(model_cls)

            if file is None:
                for transformer in vtr.get_transformers(PreDeleteFileTransformer, model_cls, transformers):
                    result = await transformer.pre_delete_file(
                        request, model_cls.meta.tablename, record.id, field, record, ctx
                    )
                    global_storage = global_storage if result is None else result

                if authorize is not None:
                    authorize(ctx)

                writes[field] = FileWrite(previous, None, global_storage)
                setattr(record, field, None)
                continue

            try:
                await storage.optimize_upload(file, stored_image_of(model_cls, field))
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None

            for transformer in vtr.get_transformers(PreUploadTransformer, model_cls, transformers):
                result = await transformer.pre_upload(request, record, field, cast(UploadFile, file), ctx)
                global_storage = global_storage if result is None else result

            if authorize is not None:
                authorize(ctx)

            try:
                path = await storage.upload(file, generate_metadata_name(model_cls), global_storage=global_storage)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from None

            writes[field] = FileWrite(previous, path, global_storage)
            setattr(record, field, path)
    except BaseException:
        await discard_file_writes(writes)
        raise

    return writes


async def end_file_writes(
    request: Request,
    model_cls: Any,
    record: Any,
    writes: FileWrites,
    ctx: dict[str, Any],
    transformers: list[type[BaseViewTransformer]] | None = None,
    previous_paths: dict[str, str | None] | None = None,
) -> None:
    """Once ``record`` is written: the post-upload and post-delete-file transformers, and the cleanup, once the
    transaction commits, of each file it let go (see schedule_file_cleanup): the one a write replaced or removed, and
    the one in ``previous_paths`` a path written over. The path the post-upload transformers give each stored file
    lands in ``ctx["uploaded_paths"]``."""
    vtr = get_service(ViewTransformerRegistry)
    let_go = {field: (path, is_global_storage_model(model_cls)) for field, path in (previous_paths or {}).items()}

    for field, write in writes.items():
        let_go[field] = (write.previous, write.global_storage)

        if write.path is not None:
            path = write.path

            for transformer in vtr.get_transformers(PostUploadTransformer, model_cls, transformers):
                path = await transformer.post_upload(request, record, field, path, ctx)

            ctx.setdefault("uploaded_paths", {})[field] = path
        else:
            for transformer in vtr.get_transformers(PostDeleteFileTransformer, model_cls, transformers):
                await transformer.post_delete_file(request, model_cls.meta.tablename, record.id, field, record, ctx)

    for field, (path, global_storage) in let_go.items():
        if path != getattr(record, field, None):
            schedule_file_cleanup(model_cls, field, path, global_storage)


async def discard_file_writes(writes: FileWrites) -> None:
    """Remove the files stored for a record that is not written."""
    storage = get_service(Storage)

    for write in writes.values():
        if write.path is not None:
            await storage.delete(write.path, global_storage=write.global_storage)


def file_paths(model_cls: Any, record: Any, values: dict[str, Any]) -> dict[str, str | None]:
    """The paths ``record`` holds in the file fields ``values`` writes, before they are written."""
    return {
        name: getattr(record, name, None) for name in values if isinstance(model_cls.meta.fields.get(name), FileField)
    }


__all__ = [
    "FileUploads",
    "FileWrite",
    "FileWrites",
    "begin_file_writes",
    "discard_file_writes",
    "end_file_writes",
    "file_paths",
    "take_file_writes",
]
