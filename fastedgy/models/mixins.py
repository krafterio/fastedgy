# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from edgy import fields, Model
from typing import Any

from pydantic import ConfigDict

from fastedgy import context


class WorkspaceableMixin(Model):
    """
    Mixin to automatically add a workspace relationship field.

    This mixin adds a foreign key relationship to the Workspace model, making it easy
    to associate any model with a specific workspace.

    Usage:
        class MyModel(BaseModel, WorkspaceableMixin):
            # Your model fields here
            pass
    """

    class Meta:
        abstract = True

    model_config = ConfigDict(
        extra='ignore',
    )

    workspace = fields.ForeignKey(
        "Workspace",
        on_delete="CASCADE",
        related_name="+",  # "+" means no reverse relation is created
        exclude=True,
        null=True,
        label="Espace de travail",
    )

    # This is a class method that will be called when the model is being created
    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        This method is called when a class inherits from WorkspaceMixin.
        It ensures the workspace field is properly set up.
        """
        super().__init_subclass__(**kwargs)

        # If the model has a Meta class, we can customize the related_name
        if hasattr(cls, "Meta") and hasattr(cls.Meta, "tablename"):
            # Get the table name from the Meta class
            tablename = cls.Meta.tablename

            # Override the workspace field with a custom related_name based on the table name
            cls.workspace = fields.ForeignKey(
                "Workspace",
                on_delete="CASCADE",
                related_name=tablename,  # This creates a reverse relation named after the table
                exclude=True,
            )

    async def save(self: Model, force_insert: bool = False, values: dict[str, Any] | set[str] | None = None,
                   force_save: bool | None = None) -> Model:
        workspace = context.get_workspace()

        if workspace and (not hasattr(self, "workspace") or self.workspace != workspace):
            self.workspace = workspace

        return await super().save(force_insert, values, force_save)


class BlameableMixin(Model):
    """
    Mixin to automatically add created_by and updated_by fields.

    This mixin adds foreign key relationships to track which user created
    and last updated the record.

    Usage:
        class MyModel(BaseModel, BlameableMixin):
            # Your model fields here
            pass
    """

    class Meta:
        abstract = True

    model_config = ConfigDict(
        extra='ignore',
    )

    created_by = fields.ForeignKey(
        "User",
        on_delete="SET NULL",
        null=True,
        related_name=False,
        label="Créé par"
    )

    updated_by = fields.ForeignKey(
        "User",
        on_delete="SET NULL",
        null=True,
        related_name=False,
        label="Mis à jour par"
    )

    async def save(self: Model, force_insert: bool = False, values: dict[str, Any] | set[str] | None = None,
                   force_save: bool | None = None) -> Model:
        current_user = context.get_user()

        if current_user:
            if not hasattr(self, "id") or not self.id:
                self.created_by = current_user
            self.updated_by = current_user

        return await super().save(force_insert, values, force_save)


__all__ = [
    "WorkspaceableMixin",
    "BlameableMixin",
]
