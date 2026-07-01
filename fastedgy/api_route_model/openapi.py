# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

"""Post-processing of the generated OpenAPI document."""

from typing import Any


def _collect_schema_refs(node: Any, acc: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and "/schemas/" in ref:
            acc.add(ref.rsplit("/", 1)[-1])
        for value in node.values():
            _collect_schema_refs(value, acc)
    elif isinstance(node, list):
        for value in node:
            _collect_schema_refs(value, acc)


def prune_orphan_schemas(spec: dict[str, Any]) -> None:
    """Drop component schemas nothing references.

    Edgy registers a junction model for every many-to-many (``<Model><Rel>Through``);
    FastAPI collects it while introspecting the relation field, but nothing in the API
    ever references it — it stays an orphan definition in the document."""
    components = spec.get("components") or {}
    schemas = components.get("schemas")
    if not schemas:
        return

    roots: set[str] = set()
    for key, value in spec.items():
        if key != "components":
            _collect_schema_refs(value, roots)
    for key, value in components.items():
        if key != "schemas":
            _collect_schema_refs(value, roots)

    reachable: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in reachable or name not in schemas:
            continue
        reachable.add(name)
        deps: set[str] = set()
        _collect_schema_refs(schemas[name], deps)
        stack.extend(deps)

    for name in [name for name in schemas if name not in reachable]:
        del schemas[name]


__all__ = [
    "prune_orphan_schemas",
]
