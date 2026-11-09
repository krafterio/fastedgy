# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from sqlalchemy import literal, select

from fastedgy import context
from fastedgy.dependencies import get_service
from fastedgy.http import Request
from fastedgy.metadata_model.generator import generate_metadata_name
from fastedgy.models.base import BaseView
from fastedgy.models.workspace import BaseWorkspace
from fastedgy.orm import Registry
from fastedgy.orm.fields import ImageField, StoredImage
from fastedgy.orm.filter import And, R
from fastedgy.orm.transaction import with_transaction
from fastedgy.storage.routing import is_global_storage_path
from fastedgy.storage.services import RewrittenImage, Storage

logger = logging.getLogger("fastedgy.storage")

type ImageColumn = tuple[Any, str]
type StoredFile = tuple[int | None, str]


@dataclass
class StoredImagesReport:
    """What a pass over the stored images found: the files each image field holds, and what became of them."""

    files: dict[str, int] = field(default_factory=dict)
    optimized: int = 0
    unchanged: int = 0
    missing: int = 0
    failed: int = 0
    bytes_before: int = 0
    bytes_after: int = 0

    def lines(self) -> list[str]:
        lines = [f"{name}: {count} file(s)" for name, count in sorted(self.files.items())]
        lines.append(
            f"Optimized: {self.optimized}, unchanged: {self.unchanged}, missing: {self.missing}, failed: {self.failed}"
        )

        if self.optimized:
            lines.append(f"Size: {self.bytes_before / 1024**2:.1f} MiB -> {self.bytes_after / 1024**2:.1f} MiB")

        return lines


def image_columns() -> list[ImageColumn]:
    """Every ImageField of the registered models, as (model, field)."""
    return [
        (model_cls, name)
        for model_cls in get_service(Registry).models.values()
        if not issubclass(model_cls, BaseView)
        for name, model_field in model_cls.meta.fields.items()
        if isinstance(model_field, ImageField)
    ]


async def optimize_stored_images(*, dry_run: bool = False, model: str | None = None) -> StoredImagesReport:
    """Rewrite the stored images of every ImageField the way an upload is optimized. Each file is rewritten once,
    every image column holding its path is pointed to the new one, then the old file and its cached variants go.

    ``model`` (metadata or table name) limits the pass to the files its image fields hold, ``dry_run`` only counts
    them."""
    holders = await _holders(image_columns())
    selected = {
        stored: columns
        for stored, columns in holders.items()
        if model is None or any(matches_model(model_cls, model) for model_cls, _ in columns)
    }
    report = StoredImagesReport()

    for columns in selected.values():
        for model_cls, name in columns:
            if model is None or matches_model(model_cls, model):
                key = f"{generate_metadata_name(model_cls)}.{name}"
                report.files[key] = report.files.get(key, 0) + 1

    if dry_run:
        return report

    with _request_context():
        current: int | None = None

        for (workspace_id, path), columns in sorted(selected.items(), key=lambda item: (item[0][0] or 0, item[0][1])):
            if workspace_id != current:
                context.set_workspace(await _workspace(workspace_id))
                current = workspace_id

            model_cls, name = columns[0]
            await rewrite_stored_image(
                report,
                path,
                model_cls.meta.fields[name].stored_image,
                partial(_repoint, columns, workspace_id, path),
                global_storage=workspace_id is None,
            )

    return report


async def rewrite_stored_image(
    report: StoredImagesReport,
    path: str,
    image: StoredImage,
    repoint: Callable[[RewrittenImage], Awaitable[Any]],
    global_storage: bool = False,
) -> RewrittenImage | None:
    """Rewrite one stored image as ``image`` asks, point what holds it to the new file with ``repoint``, run in a
    transaction, then remove the old file and its cached variants. The outcome is counted in ``report``, and the new
    file goes when ``repoint`` fails."""
    storage = get_service(Storage)

    try:
        rewritten = await storage.optimize_stored_image(path, image, global_storage)
    except FileNotFoundError:
        report.missing += 1
        return None
    except Exception as e:
        logger.warning(f"Cannot optimize the stored image {path}: {e!r}")
        report.failed += 1
        return None

    if rewritten is None:
        report.unchanged += 1
        return None

    try:
        await with_transaction(lambda: repoint(rewritten))
    except Exception as e:
        logger.warning(f"Cannot point the records of {path} to {rewritten.path}: {e!r}")
        await storage.delete(rewritten.path, global_storage=global_storage)
        report.failed += 1
        return None

    await storage.delete(path, global_storage=global_storage)
    report.optimized += 1
    report.bytes_before += rewritten.size_before
    report.bytes_after += rewritten.size_after

    return rewritten


async def _repoint(columns: list[ImageColumn], workspace_id: int | None, path: str, rewritten: RewrittenImage) -> None:
    for model_cls, name in columns:
        rule = R(name, "=", path)

        if workspace_id is not None and "workspace" in model_cls.meta.fields:
            rule = And(rule, R("workspace", "=", workspace_id))

        await model_cls.global_query.filter(rule, allow_excluded=True).update(**{name: rewritten.path})


async def _holders(columns: list[ImageColumn]) -> dict[StoredFile, list[ImageColumn]]:
    """The stored files the image columns hold, each with the columns holding it. A file is named by its path and the
    workspace whose storage holds it, None for the global storage, which the path decides as downloads do."""
    database = get_service(Registry).database
    global_segments: dict[str, bool] = {}
    holders: dict[StoredFile, list[ImageColumn]] = defaultdict(list)

    for model_cls, name in columns:
        table = model_cls.table
        column = table.c[name]
        workspace = table.c.workspace if "workspace" in model_cls.meta.fields else literal(None)
        query = select(column, workspace).distinct().where(column.is_not(None), column != "")

        for path, workspace_id in await database.fetch_all(query):
            segment = path.split("/", 1)[0]

            if segment not in global_segments:
                global_segments[segment] = await is_global_storage_path(path)

            holders[(None if global_segments[segment] else workspace_id, path)].append((model_cls, name))

    return holders


def matches_model(model_cls: Any, name: str) -> bool:
    """Whether ``name`` is the metadata name, the table name or the class name of the model."""
    return name in (generate_metadata_name(model_cls), model_cls.meta.tablename, model_cls.__name__)


@contextmanager
def _request_context() -> Iterator[None]:
    token = context.set_request(
        Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": []})
    )

    try:
        yield
    finally:
        context.reset_request(token)


async def _workspace(workspace_id: int | None) -> Any:
    if workspace_id is None:
        return None

    workspace_cls = next(
        model_cls for model_cls in get_service(Registry).models.values() if issubclass(model_cls, BaseWorkspace)
    )

    return await workspace_cls.global_query.filter(R("id", "=", workspace_id)).first()


__all__ = [
    "StoredImagesReport",
    "image_columns",
    "matches_model",
    "optimize_stored_images",
    "rewrite_stored_image",
]
