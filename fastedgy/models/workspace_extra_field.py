# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, NoReturn

from fastapi import HTTPException

from fastedgy.i18n import _t, _ts
from fastedgy.models.base import BaseModel
from fastedgy.models.extra_field_model import WorkspaceExtraFieldModel
from fastedgy.models.mixins import WorkspaceableMixin
from fastedgy.models.queued_task import OrderByList
from fastedgy.orm import fields
from fastedgy.orm.fields.field_choice import ExtendableChoiceEnum


class WorkspaceExtraFieldType(ExtendableChoiceEnum):
    boolean = _ts("Boolean")
    char = _ts("Char")
    choice = _ts("List of values")
    date = _ts("Date")
    datetime = _ts("Datetime")
    duration = _ts("Duration")
    email = _ts("Email")
    float = _ts("Float")
    html = _ts("HTML")
    integer = _ts("Integer")
    ip_address = _ts("IP address")
    phone = _ts("Phone")
    rich_text = _ts("Rich text")
    text = _ts("Text")
    time = _ts("Time")
    url = _ts("Link")
    uuid = _ts("UUID")


EXTRA_FIELDS_MAP = {
    WorkspaceExtraFieldType.boolean: fields.BooleanField,
    WorkspaceExtraFieldType.char: fields.CharField,
    WorkspaceExtraFieldType.choice: fields.CharField,
    WorkspaceExtraFieldType.date: fields.DateField,
    WorkspaceExtraFieldType.datetime: fields.DateTimeField,
    WorkspaceExtraFieldType.duration: fields.DurationField,
    WorkspaceExtraFieldType.email: fields.EmailField,
    WorkspaceExtraFieldType.float: fields.FloatField,
    WorkspaceExtraFieldType.html: fields.HTMLField,
    WorkspaceExtraFieldType.integer: fields.IntegerField,
    WorkspaceExtraFieldType.ip_address: fields.IPAddressField,
    WorkspaceExtraFieldType.phone: fields.PhoneField,
    WorkspaceExtraFieldType.rich_text: fields.RichTextField,
    WorkspaceExtraFieldType.text: fields.TextField,
    WorkspaceExtraFieldType.time: fields.TimeField,
    WorkspaceExtraFieldType.url: fields.URLField,
    WorkspaceExtraFieldType.uuid: fields.UUIDField,
}

EXTRA_FIELD_TYPE_OPTIONS = {
    WorkspaceExtraFieldType.boolean: {},
    WorkspaceExtraFieldType.char: {
        "max_length": 255,
    },
    WorkspaceExtraFieldType.choice: {
        "max_length": 255,
    },
    WorkspaceExtraFieldType.date: {},
    WorkspaceExtraFieldType.datetime: {},
    WorkspaceExtraFieldType.duration: {},
    WorkspaceExtraFieldType.email: {
        "max_length": 255,
    },
    WorkspaceExtraFieldType.float: {},
    WorkspaceExtraFieldType.html: {
        "max_length": 65535,
    },
    WorkspaceExtraFieldType.integer: {},
    WorkspaceExtraFieldType.ip_address: {},
    WorkspaceExtraFieldType.phone: {
        "max_length": 50,
    },
    WorkspaceExtraFieldType.rich_text: {
        "max_length": 65535,
    },
    WorkspaceExtraFieldType.text: {
        "max_length": 255,
    },
    WorkspaceExtraFieldType.time: {},
    WorkspaceExtraFieldType.url: {
        "max_length": 255,
    },
    WorkspaceExtraFieldType.uuid: {},
}


def option_value(option: Any) -> str:
    return str(option.get("value", "") if isinstance(option, dict) else option)


def option_color(option: Any) -> int | None:
    color = option.get("color") if isinstance(option, dict) else None

    return color if isinstance(color, int) and not isinstance(color, bool) else None


class BaseWorkspaceExtraField(BaseModel, WorkspaceableMixin):
    class Meta(BaseModel.Meta, WorkspaceableMixin.Meta):
        abstract = True
        label = _ts("Custom field")
        label_plural = _ts("Custom fields")
        default_order_by: OrderByList = [("label", "asc")]
        unique_together = [
            ("workspace", "model", "name"),
        ]
        indexes = [
            fields.Index(fields=["workspace", "model"], suffix="idx_workspace_extra_fields"),
        ]

    label: str | None = fields.CharField(max_length=255, label=_ts("Label"))

    name: str | None = fields.CharField(max_length=40, label=_ts("Technical name"))

    model: WorkspaceExtraFieldModel | None = fields.ChoiceField(
        WorkspaceExtraFieldModel,
        null=True,
        label=_ts("Model"),
    )
    """The model this field is added to.

    The choices are not written anywhere: a model joins them by holding the
    `extra` column the values live in, which `ExtendableMixin` is the shortest
    way to bring. `MetadataModel.has_extra_fields` says the same thing to a
    client."""

    field_type: WorkspaceExtraFieldType | None = fields.ChoiceField(WorkspaceExtraFieldType, label=_ts("Type"))

    required: bool = fields.BooleanField(default=False, label=_ts("Required"))

    options: list[Any] | None = fields.JSONField(
        null=True,
        label=_ts("Values"),
        help_text=_ts(
            'The accepted values, for a field of type "List of values". Ignored elsewhere. '
            'Either strings, ["Seed", "Series A"], or objects carrying a colour index: '
            '[{"value": "Seed", "color": 3}]. The colour is optional, but it is optional for '
            "the whole list: a half-coloured list is refused."
        ),
    )

    def option_values(self) -> list[str]:
        return [option_value(option) for option in (getattr(self, "options", None) or [])]

    def metadata_choices(self) -> dict[str, str] | None:
        if getattr(self, "field_type", None) != WorkspaceExtraFieldType.choice:
            return None

        return {value: value for value in self.option_values()} or None

    async def save(
        self,
        force_insert: bool = False,
        values: dict[str, Any] | set[str] | None = None,
        force_save: bool | None = None,
    ) -> Any:
        # The stored row is only worth reading when the list of values can have
        # moved. Renaming a field of any other type would otherwise pay a
        # select for nothing, on every write.
        options = getattr(self, "options", None)
        concerns_options = getattr(self, "field_type", None) == WorkspaceExtraFieldType.choice or options
        stored = await type(self).query.get_or_none(id=self.pk) if self.pk and concerns_options else None
        changed = stored is None or getattr(stored, "options", None) != options

        # An update that leaves `options` alone must not fail on a list written
        # before this rule, or nobody could ever rename a field again.
        if changed:
            self._check_options()

        if stored is not None and changed:
            await self._forget_dropped_options(stored)

        saved = await super().save(force_insert, values, force_save)
        await self._forget_cache()

        return saved

    async def delete(self, skip_post_delete_hooks: bool = False) -> Any:
        """Take the values off the records before the field that declared them
        goes away.

        The `extra` column is free-form JSON: nothing else would clear the key,
        it would stay in every record out of reach of the API and of the agent,
        and come back as it was if the workspace redeclared a field of the same
        name."""
        await self._rewrite(None)
        deleted = await super().delete(skip_post_delete_hooks)
        await self._forget_cache()

        return deleted

    async def _forget_cache(self) -> None:
        """This worker forgets what it read at once, the others are told to."""
        from fastedgy.orm.extra_fields import announce_workspace_extra_fields, invalidate_workspace_extra_fields

        workspace_id = getattr(self, "workspace_id", None) or getattr(getattr(self, "workspace", None), "id", None)

        invalidate_workspace_extra_fields(workspace_id)

        if workspace_id is not None:
            await announce_workspace_extra_fields(workspace_id)

    def _check_options(self) -> None:
        """Refuse a list of values the field could not display.

        `options` is a JSON column, so nothing validates it on its own. The
        colour is optional for the list, not for one option: a client renders a
        chip for what carries a colour and bare text for what does not, so a
        mixed list displays broken with nothing having said so at write time."""
        if getattr(self, "field_type", None) != WorkspaceExtraFieldType.choice:
            return

        label = str(getattr(self, "label", None) or getattr(self, "name", None) or "")
        options = getattr(self, "options", None)

        if not isinstance(options, list) or not options:
            _refuse_options(label, _t("at least one value"))

        from fastedgy.config import BaseSettings
        from fastedgy.dependencies import get_service

        seen: set[str] = set()
        colored: list[str] = []
        plain: list[str] = []
        colors = get_service(BaseSettings).workspace_extra_field_option_colors

        for option in options:
            if not isinstance(option, str | dict):
                _refuse_options(label, _t("strings or objects carrying a value and a colour"))

            value = option_value(option)

            if not value.strip():
                _refuse_options(label, _t("a non-empty text"))

            if value in seen:
                _refuse_options(label, _t("distinct values: {value} appears twice", value=value))

            seen.add(value)

            if not isinstance(option, dict) or "color" not in option:
                plain.append(value)
                continue

            color = option_color(option)

            if color is None or color < 0 or (colors and color >= len(colors)):
                _refuse_options(
                    label,
                    _t("a colour from 0 to {last}", last=len(colors) - 1) if colors else _t("a colour index"),
                )

            colored.append(value)

        if colored and plain:
            _refuse_options(label, _t("a colour on all of them or on none: {value} has none", value=plain[0]))

    async def _forget_dropped_options(self, stored: Any) -> None:
        """Take off the records a value the workspace just dropped from the field.

        Without this the record keeps a string the field no longer knows: it
        shows without its chip, filters no longer match it, and nothing says it
        is orphaned. The list of options is the only authority on what exists."""
        dropped = {option_value(option) for option in (getattr(stored, "options", None) or [])} - set(
            self.option_values()
        )

        if dropped:
            await self._rewrite(dropped)

    async def _rewrite(self, dropped: set[str] | None) -> None:
        """Take the field, or some of its values, off the records it was written on.

        `dropped` names the values to clear; None drops the key itself. One
        statement per value rather than one per record: a workspace removes an
        option or two, it may hold a hundred thousand records, and reading them
        all into memory to save them back one by one is not a price a change of
        declaration should pay.

        Nothing is saved through the model, so no per-record event is emitted:
        the change belongs to the field, and it is the field's own event a
        client listens to before reading its metadata again.
        """
        from sqlalchemy import text

        from fastedgy.dependencies import get_service
        from fastedgy.orm import Registry
        from fastedgy.orm.extra_fields import extendable_models

        model_cls = extendable_models().get(getattr(getattr(self, "model", None), "name", ""))
        name = str(getattr(self, "name", "") or "")

        if model_cls is None or not name:
            return

        table = str(model_cls.meta.tablename)
        fields = model_cls.meta.fields
        workspace_id = getattr(self, "workspace_id", None) or getattr(getattr(self, "workspace", None), "id", None)

        scope = " AND workspace = :workspace" if workspace_id is not None and "workspace" in fields else ""
        touched = ", updated_at = NOW()" if "updated_at" in fields else ""
        database = get_service(Registry).database

        # `jsonb_exists` rather than the `?` operator, which a driver reading
        # its own placeholders would take for one.
        for value in [None] if dropped is None else sorted(dropped):
            if value is None:
                change = "extra = (extra::jsonb - :name)::json"
                match = "jsonb_exists(extra::jsonb, :name)"
                params: dict[str, Any] = {"name": name}
            else:
                change = "extra = jsonb_set(extra::jsonb, ARRAY[:name], 'null')::json"
                match = "extra::jsonb ->> :name = :value"
                params = {"name": name, "value": value}

            if scope:
                params["workspace"] = workspace_id

            sql = text(f"UPDATE {table} SET {change}{touched} WHERE extra IS NOT NULL AND {match}{scope}")

            await database.execute(sql.bindparams(**params))


def _refuse_options(label: str, expected: Any) -> NoReturn:
    raise HTTPException(
        status_code=422,
        detail=_t("The values of field {field} expect {expected}.", field=label, expected=expected),
    )


__all__ = [
    "EXTRA_FIELDS_MAP",
    "EXTRA_FIELD_TYPE_OPTIONS",
    "BaseWorkspaceExtraField",
    "WorkspaceExtraFieldType",
    "option_color",
    "option_value",
]
