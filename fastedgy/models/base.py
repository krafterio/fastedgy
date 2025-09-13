# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import abstractmethod
from typing import ClassVar, Optional, Union, TYPE_CHECKING

from datetime import datetime

from fastedgy.orm import Model, fields
from fastedgy.orm.manager import Manager, BaseManager, WorkspaceableManager, WorkspaceableRedirectManager
from fastedgy.orm.view import create_view

from pydantic import ConfigDict

from sqlalchemy import MetaData, Selectable, Table

if TYPE_CHECKING:
    from fastedgy.orm.query import QuerySet


class BaseModel(Model):
    id: int | None = fields.IntegerField(primary_key=True, label="ID") # type: ignore
    created_at: datetime | None = fields.DateTimeField(default_factory=datetime.now, read_only=True, auto_now_add=True, label="Créé le") # type: ignore
    updated_at: datetime | None = fields.DateTimeField(default_factory=datetime.now, auto_now=True, label="Mis à jour le") # type: ignore

    class Meta:
        from fastedgy.orm import Registry
        from fastedgy.dependencies import get_service
        abstract = True
        registry = get_service(Registry)
        exclude_secrets = True

    model_config = ConfigDict(
        extra='ignore',
    )

    query: ClassVar[Union[WorkspaceableManager, 'QuerySet']] = WorkspaceableManager()
    query_related: ClassVar[Union[WorkspaceableRedirectManager, 'QuerySet']] = WorkspaceableRedirectManager(redirect_name="query")
    global_query: ClassVar[Union[Manager, 'QuerySet']] = Manager()


class BaseView(Model):
    """
    Base class for defining SQL views.

    This class allows you to define SQL views directly in ORM models, without them being treated as tables by Alembic.

    Example usage:

    ```python
    from fastedgy.orm import fields
    from sqlalchemy import literal, null, select, Selectable
    from models.contact import Contact
    from models.user import User


    class MergedUserContactView(BaseView):
        class Meta:
            tablename = "merged_user_contact_view"

        # Common Fields
        id: int = fields.IntegerField(primary_key=True)
        name: str = fields.CharField(max_length=255)
        active: bool = fields.BooleanField(default=True)

        # Contact Fields
        first_name: str | None = fields.CharField(max_length=255, null=True)
        last_name: str | None = fields.CharField(max_length=255, null=True)

        @classmethod
        def view_query(cls) -> Selectable:
            user_select = select(
                literal('user').label('source_type'),
                User.columns.id,
                User.columns.name,
                null().label('first_name'),
                null().label('last_name'),
            ).where(
                User.columns.active == True
            )

            contact_select = select(
                literal('contact').label('source_type'),
                Contact.columns.id,
                Contact.columns.full_name.label('name'),
                Contact.columns.first_name,
                Contact.columns.last_name,
            ).where(
                Contact.columns.active == True
            )

            return user_select.union(contact_select)
    ```
    """
    class Meta:
        from fastedgy.orm import Registry
        from fastedgy.dependencies import get_service
        abstract = True
        registry = get_service(Registry)
        exclude_secrets = True
        is_view = True

    query: ClassVar[Union[WorkspaceableManager, 'QuerySet']] = WorkspaceableManager()
    query_related: ClassVar[Union[WorkspaceableRedirectManager, 'QuerySet']] = WorkspaceableRedirectManager(redirect_name="query")
    global_query: ClassVar[Union[Manager, 'QuerySet']] = Manager()

    @classmethod
    def build(
            cls,
            schema: Optional[str] = None,
            metadata: Optional[MetaData] = None,
    ) -> Table:
        return create_view(
            name=cls.meta.tablename,
            selectable=cls.view_query(),
            metadata=metadata,
            replace=True,
        )

    @classmethod
    @abstractmethod
    def view_query(cls) -> Selectable:
        pass


__all__ = [
    "BaseModel",
    "BaseView",
]
