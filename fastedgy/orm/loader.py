# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import io
import mimetypes
import os

from dataclasses import dataclass, field
from glob import glob
from pathlib import Path
from typing import Any, cast

from starlette.datastructures import Headers, UploadFile

from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service
from fastedgy.metadata_model.generator import generate_metadata_name
from fastedgy.models.base import BaseModel
from fastedgy.models.data_record import DataRecord
from fastedgy.orm import Registry, with_transaction
from fastedgy.storage import Storage
from fastedgy.storage.routing import is_global_storage_model


@dataclass(frozen=True)
class IdRef:
    key: str


@dataclass(frozen=True)
class Ref:
    key: str


@dataclass(frozen=True)
class FileRef:
    path: str


id = IdRef
ref = Ref
file = FileRef


@dataclass
class LoadReport:
    created: int = 0
    updated: int = 0


@dataclass
class _Record:
    key: str
    model_cls: type[BaseModel]
    model_name: str
    payload: dict[str, Any] = field(default_factory=dict)


def _build_model_map(registry: Registry) -> dict[str, type[BaseModel]]:
    model_map: dict[str, type[BaseModel]] = {}

    for model_cls in registry.models.values():
        typed = cast(type[BaseModel], model_cls)
        model_map[str(typed.meta.tablename)] = typed
        model_map[generate_metadata_name(typed)] = typed

    return model_map


def _read_records(path: str) -> list[dict[str, Any]]:
    namespace: dict[str, Any] = {}
    exec(compile(Path(path).read_text(encoding="utf-8"), path, "exec"), namespace)
    data = namespace.get("data", [])

    if not isinstance(data, list):
        raise ValueError(f"'data' in {path} must be a list of records")

    return data


def _extract_key(entry: dict[str, Any], source: str) -> tuple[str, dict[str, Any]]:
    marker = entry.get("id")

    if not isinstance(marker, IdRef):
        raise ValueError(f'Each record in {source} must declare its key via id("...") in the "id" field')

    payload = {name: value for name, value in entry.items() if name != "id"}

    return marker.key, payload


def _ref_keys(payload: dict[str, Any]) -> set[str]:
    keys: set[str] = set()

    for value in payload.values():
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, Ref):
                keys.add(item.key)

    return keys


def _topo_sort(records: list[_Record]) -> list[_Record]:
    by_key = {record.key: record for record in records}
    ordered: list[_Record] = []
    state: dict[str, int] = {}

    def visit(record: _Record, stack: list[str]) -> None:
        status = state.get(record.key)

        if status == 1:
            return

        if status == 0:
            raise ValueError(f"Circular reference in data records: {' -> '.join([*stack, record.key])}")

        state[record.key] = 0

        for dependency in _ref_keys(record.payload):
            target = by_key.get(dependency)

            if target is not None:
                visit(target, [*stack, record.key])

        state[record.key] = 1
        ordered.append(record)

    for record in records:
        visit(record, [])

    return ordered


async def _resolve_ref(ref: Ref, resolved: dict[str, int]) -> int:
    if ref.key in resolved:
        return resolved[ref.key]

    existing = await DataRecord.query.get_or_none(key=ref.key)

    if existing is None:
        raise ValueError(f'Unknown ref("{ref.key}")')

    resolved[ref.key] = existing.record_id

    return existing.record_id


async def _upload_file(model_cls: type[BaseModel], file_ref: FileRef, server_path: str) -> str:
    storage = get_service(Storage)
    resolved_path = os.path.normpath(os.path.join(server_path, file_ref.path))

    with open(resolved_path, "rb") as handle:
        content = handle.read()

    filename = os.path.basename(resolved_path)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    upload = UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))

    return await storage.upload(
        upload, str(model_cls.meta.tablename), global_storage=is_global_storage_model(model_cls)
    )


async def _apply_record(
    record: _Record,
    resolved: dict[str, int],
    server_path: str,
    report: LoadReport,
) -> None:
    model_cls = record.model_cls
    scalars: dict[str, Any] = {}
    relations: dict[str, list[int]] = {}
    files: dict[str, FileRef] = {}

    for name, value in record.payload.items():
        edgy_field = model_cls.meta.fields.get(name)
        is_m2m = getattr(edgy_field, "is_m2m", False)
        is_many2one = edgy_field is not None and hasattr(edgy_field, "target") and not is_m2m
        is_collection = edgy_field is not None and not is_many2one and (is_m2m or hasattr(edgy_field, "related_from"))

        if is_collection:
            ids: list[int] = []

            for item in value if isinstance(value, list) else [value]:
                ids.append(await _resolve_ref(item, resolved) if isinstance(item, Ref) else int(item))

            relations[name] = ids
        elif isinstance(value, Ref):
            scalars[name] = await _resolve_ref(value, resolved)
        elif isinstance(value, FileRef):
            files[name] = value
        else:
            scalars[name] = value

    data_record = await DataRecord.query.get_or_none(key=record.key)
    existing = None

    if data_record is not None:
        existing = await model_cls.query.get_or_none(id=data_record.record_id)

    for name, file_ref in files.items():
        if existing is None or not getattr(existing, name, None):
            scalars[name] = await _upload_file(model_cls, file_ref, server_path)

    if existing is not None:
        changed = False

        for name, value in scalars.items():
            current = getattr(existing, name, None)
            current = getattr(current, "id", current)

            if current != value:
                setattr(existing, name, value)
                changed = True

        if changed:
            await existing.save()
            report.updated += 1

        instance = existing
    else:
        instance = await model_cls.query.create(**scalars)
        report.created += 1

    if data_record is None:
        await DataRecord.query.create(key=record.key, model=record.model_name, record_id=instance.id)
    elif data_record.record_id != instance.id:
        data_record.record_id = instance.id
        await data_record.save()

    for name, ids in relations.items():
        relation = getattr(instance, name)
        target = set(ids)
        current = await relation.all()
        current_ids = {item.id for item in current}

        for item in current:
            if item.id not in target:
                await relation.remove(item)

        for related_id in ids:
            if related_id not in current_ids:
                await relation.add(await relation.to.query.get(id=related_id))

    resolved[record.key] = instance.id


async def load_data(data_dir: str | None = None) -> LoadReport:
    settings = get_service(BaseSettings)
    server_path = settings.server_path

    if data_dir is None:
        data_dir = os.path.join(server_path, "data")

    report = LoadReport()

    if not os.path.isdir(data_dir):
        return report

    registry = get_service(Registry)
    model_map = _build_model_map(registry)

    records: list[_Record] = []

    for file_path in sorted(glob(os.path.join(data_dir, "*.py"))):
        stem = Path(file_path).stem

        if stem.startswith("_"):
            continue

        model_cls = model_map.get(stem)

        if model_cls is None:
            raise ValueError(f"No model matches data file '{stem}.py'")

        model_name = generate_metadata_name(model_cls)

        for entry in _read_records(file_path):
            key, payload = _extract_key(entry, file_path)
            records.append(_Record(key=key, model_cls=model_cls, model_name=model_name, payload=payload))

    ordered = _topo_sort(records)

    async def run() -> None:
        report.created = 0
        report.updated = 0
        resolved: dict[str, int] = {}

        for record in ordered:
            await _apply_record(record, resolved, server_path, report)

    await with_transaction(run)

    return report


__all__ = [
    "IdRef",
    "Ref",
    "FileRef",
    "LoadReport",
    "load_data",
    "id",
    "ref",
    "file",
]
