# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from enum import Enum
from typing import TYPE_CHECKING, Union, Any
import contextlib

from fastedgy.models.base import BaseModel
from fastedgy.i18n import _ts, _t
from fastedgy.orm import Model, Registry, fields
from fastedgy.orm.signals import (
    pre_save,
    pre_update,
    post_update,
    pre_delete,
    post_delete,
)

from fastedgy.dependencies import get_service

if TYPE_CHECKING:
    from fastedgy.models.attachment import BaseAttachment as Attachment


class AttachmentMixin(BaseModel):
    class Meta(BaseModel.Meta):
        abstract = True
        label = _ts("Pièce jointe")
        label_plural = _ts("Pièces jointes")
        indexes = [
            fields.Index(fields=["parent"]),
        ]
        unique_together = [
            fields.UniqueConstraint(
                fields=["parent", "name", "extension"],
                name="uq_attachment_parent_name_ext",
            )
        ]

    # Métadonnées principales
    name: str = fields.CharField(
        max_length=255,
        label=_ts("Nom"),
    )  # type: ignore

    extension: str | None = fields.CharField(
        max_length=20,
        null=True,
        label=_ts("Extension"),
    )  # type: ignore

    mime_type: str | None = fields.CharField(
        max_length=150,
        null=True,
        label=_ts("Type MIME"),
    )  # type: ignore

    size_bytes: int | None = fields.BigIntegerField(
        null=True,
        label=_ts("Taille (octets)"),
    )  # type: ignore

    width: int | None = fields.IntegerField(
        null=True,
        label=_ts("Largeur"),
    )  # type: ignore

    height: int | None = fields.IntegerField(
        null=True,
        label=_ts("Hauteur"),
    )  # type: ignore

    # Storage
    storage_path: str | None = fields.CharField(
        max_length=1024,
        null=True,
        exclude=True,
        label=_ts("Chemin de stockage"),
    )  # type: ignore

    parent: Union["Attachment", None] = fields.ForeignKey(
        "Attachment",
        null=True,
        related_name="children",
        on_delete="CASCADE",
        label=_ts("Parent"),
    )  # type: ignore


class AttachmentType(str, Enum):
    file = "file"
    folder = "folder"


class AttachmentPathMixin(AttachmentMixin):
    class Meta(AttachmentMixin.Meta):
        abstract = True
        indexes = [
            fields.Index(fields=["path"]),
        ]

    # Type de nœud
    type: AttachmentType = fields.CharChoiceField(
        choices=AttachmentType,
        default=AttachmentType.file,
        label=_ts("Type"),
    )  # type: ignore

    path: str = fields.CharField(
        max_length=1500,
        index=True,
        default="",
        label=_ts("Chemin complet"),
    )  # type: ignore

    parent_ids: list[int] | None = fields.JSONField(
        null=True,
        label=_ts("Parents"),
    )  # type: ignore

    depth: int = fields.SmallIntegerField(
        default=0,
        label=_ts("Profondeur"),
    )  # type: ignore


@pre_save.connect_via(AttachmentPathMixin)
async def on_pre_save(
    sender: Any, instance: Any, model_instance: Any, **kwargs: Any
) -> None:  # noqa: ANN401
    is_update: bool = bool(kwargs.get("is_update"))
    values: dict[str, Any] = kwargs.get("values", {}) or {}
    column_values: dict[str, Any] = kwargs.get("column_values", {}) or {}

    # Lock 'type' on update
    if is_update and ("type" in values or "type" in column_values):
        raise ValueError(_t("Le champ 'type' ne peut pas être modifié"))

    # Compute path/depth/parent_ids based on current model_instance values
    name: str | None = getattr(model_instance, "name", None)
    parent = getattr(model_instance, "parent", None)

    parent_path: str | None = None
    parent_parent_ids: list[int] | None = None
    parent_id: int | None = None

    if parent is not None:
        try:
            parent_id = (
                getattr(parent, "id", None) if not isinstance(parent, int) else parent
            )
        except Exception:
            parent_id = None

        if parent_id is not None:
            from fastedgy.models.attachment import BaseAttachment as AttachmentModel

            p = await AttachmentModel.query.only(
                "id", "type", "path", "parent_ids"
            ).get(id=parent_id)

            if getattr(p, "type", None) == AttachmentType.file:
                raise ValueError(_t("Le parent ne peut pas être un fichier"))

            parent_path = p.path
            parent_parent_ids = p.parent_ids or []

    if name:
        base = parent_path.strip("/") if parent_path else ""
        path = f"{base}/{name}" if base else name
        model_instance.path = path
        model_instance.depth = path.count("/")
        model_instance.parent_ids = (
            None if parent_id is None else [*(parent_parent_ids or []), parent_id]
        )


@pre_update.connect_via(AttachmentPathMixin)
async def on_pre_update(
    sender: Any, instance: Any, model_instance: Any, **kwargs: Any
) -> None:  # noqa: ANN401
    Attachment: AttachmentPathMixin = get_service(Registry).get_model("Attachment")  # type: ignore
    if sender is not Attachment:
        return

    values: dict[str, Any] = kwargs.get("values", {}) or {}
    column_values: dict[str, Any] = kwargs.get("column_values", {}) or {}

    # lock type changes
    if "type" in values or "type" in column_values:
        raise ValueError(_t("Le champ 'type' ne peut pas être modifié"))

    # validate new parent, if any
    new_parent_id = column_values.get("parent_id", None)

    if new_parent_id is not None:
        p = await Attachment.query.only("id", "type").get(id=new_parent_id)

        if p.type == AttachmentType.file:
            raise ValueError(_t("Le parent ne peut pas être un fichier"))

    # snapshot if name or parent changes
    if ("name" in values) or ("parent" in values) or ("parent_id" in column_values):
        models = await instance  # QuerySet is awaitable -> list[Attachment]
        instance._fe_att_snapshot = {  # type: ignore[attr-defined]
            m.id: {"old_path": m.path, "old_pi": m.parent_ids or []} for m in models
        }
        instance._fe_att_new_parent_id = new_parent_id  # type: ignore[attr-defined]
        instance._fe_att_new_name = values.get("name", None)  # type: ignore[attr-defined]


@post_update.connect_via(AttachmentPathMixin)
async def on_post_update(
    sender: Any, instance: Any, model_instance: Any, **kwargs: Any
) -> None:  # noqa: ANN401
    Attachment: AttachmentPathMixin = get_service(Registry).get_model("Attachment")  # type: ignore

    if sender is not Attachment:
        return

    snapshot: dict[int, dict[str, Any]] | None = getattr(
        instance, "_fe_att_snapshot", None
    )

    if not snapshot:
        return

    new_parent_id: int | None = getattr(instance, "_fe_att_new_parent_id", None)

    # resolve new parent data once if changed
    parent_path = ""
    parent_ai: list[int] = []

    if new_parent_id is not None:
        p = await Attachment.query.only("id", "path", "parent_ids").get(
            id=new_parent_id
        )
        parent_path = p.path or ""
        parent_ai = p.parent_ids or []

    # process each updated node
    for att_id, meta in snapshot.items():
        # load node with updated DB values
        node = await Attachment.query.get(id=att_id)
        old_path: str = meta["old_path"]
        old_pi: list[int] = meta["old_pi"]

        # compute new prefix
        if new_parent_id is not None:
            base = parent_path.strip("/")
            new_prefix = f"{base}/{node.name}" if base else node.name
            new_ai = [*parent_ai, new_parent_id] if new_parent_id is not None else []
        else:
            # only rename
            base_parent = (
                (await node.parent.load_recursive())
                if getattr(node, "parent", None)
                else None
            )  # type: ignore[attr-defined]
            if base_parent:
                base = base_parent.path.strip("/")
                new_prefix = f"{base}/{node.name}" if base else node.name
                new_ai = (base_parent.parent_ids or []) + [base_parent.id]
            else:
                new_prefix = node.name
                new_ai = []

        if new_prefix != node.path:
            await Attachment.query.filter(id=att_id).update(
                path=new_prefix,
                depth=new_prefix.count("/"),
                parent_ids=(new_ai or None),
            )

        # update descendants paths
        old_prefix = old_path.rstrip("/")

        if not old_prefix:
            old_prefix = node.name  # minimal safeguard

        descendants = await Attachment.query.filter(
            path__startswith=f"{old_prefix}/"
        ).all()

        for d in descendants:
            suffix = d.path[len(old_prefix) :].lstrip("/")
            new_d_path = f"{new_prefix}/{suffix}" if suffix else new_prefix

            # recompute ancestor ids
            try:
                idx = (d.parent_ids or []).index(att_id)
            except ValueError:
                idx = -1

            if idx >= 0 and new_parent_id is not None:
                tail = (d.parent_ids or [])[idx + 1 :]
                new_d_ai = [*new_ai, att_id, *tail]
            else:
                # parent unchanged: keep same ancestor ids
                new_d_ai = d.parent_ids or []

            await Attachment.query.filter(id=d.id).update(
                path=new_d_path,
                depth=new_d_path.count("/"),
                parent_ids=(new_d_ai or None),
            )

    # cleanup snapshot
    with contextlib.suppress(Exception):  # type: ignore[name-defined]
        delattr(instance, "_fe_att_snapshot")
        delattr(instance, "_fe_att_new_parent_id")
        delattr(instance, "_fe_att_new_name")


@pre_delete.connect_via(AttachmentMixin)
async def on_pre_delete(
    sender: Any, instance: Any, model_instance: Any, **kwargs: Any
) -> None:  # noqa: ANN401
    Attachment: AttachmentMixin = get_service(Registry).get_model("Attachment")  # type: ignore

    if sender is not Attachment:
        return

    files_to_delete: list[str] = []

    try:
        # Case 1: QuerySet deletion (bulk delete)
        files = await instance.filter(type=AttachmentType.file).values(
            fields=["id", "storage_path"]
        )
        files_to_delete = [
            f.get("storage_path") for f in files if f.get("storage_path")
        ]
    except AttributeError:
        # Case 2: Single instance deletion
        if model_instance is not None:
            # Direct file
            if getattr(model_instance, "type", None) == AttachmentType.file:
                storage_path = getattr(model_instance, "storage_path", None)
                if storage_path:
                    files_to_delete.append(storage_path)

            # Files in descendants (if it's a folder)
            if getattr(model_instance, "type", None) == AttachmentType.folder:
                path = getattr(model_instance, "path", "")
                if path:
                    descendants = await Attachment.query.filter(
                        path__startswith=f"{path.rstrip('/')}/",
                        type=AttachmentType.file,
                    ).values(fields=["storage_path"])
                    for d in descendants:
                        if d.get("storage_path"):
                            files_to_delete.append(d.get("storage_path"))

    # Store files to delete for post_delete
    instance._fe_att_files_to_delete = files_to_delete  # type: ignore[attr-defined]
    if model_instance is not None:
        model_instance._fe_att_files_to_delete = files_to_delete  # type: ignore[attr-defined]


@post_delete.connect_via(AttachmentMixin)
async def on_post_delete(
    sender: Any, instance: Any, model_instance: Any, **kwargs: Any
) -> None:  # noqa: ANN401
    Attachment: AttachmentMixin = get_service(Registry).get_model("Attachment")  # type: ignore

    if sender is not Attachment:
        return

    # Try to get files from instance or model_instance
    files = getattr(instance, "_fe_att_files_to_delete", None)
    if not files and model_instance is not None:
        files = getattr(model_instance, "_fe_att_files_to_delete", None)

    if not files:
        return

    from fastedgy.storage import Storage

    storage = get_service(Storage)

    for path in files:
        try:
            await storage.delete(path)
        except Exception:
            pass

    # Clean up
    with contextlib.suppress(Exception):  # type: ignore[name-defined]
        delattr(instance, "_fe_att_files_to_delete")
        if model_instance is not None:
            delattr(model_instance, "_fe_att_files_to_delete")


__all__ = [
    "AttachmentMixin",
    "AttachmentPathMixin",
    "AttachmentType",
    "on_pre_save",
    "on_post_update",
    "on_pre_update",
    "on_pre_delete",
    "on_post_delete",
]
