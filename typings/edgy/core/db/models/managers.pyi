from typing import Any

from edgy.core.db.models.types import BaseModelType
from edgy.core.db.querysets.queryset import QuerySet

class BaseManager:
    queryset_class: type[QuerySet]
    owner: type[BaseModelType] | None
    inherit: bool
    name: str
    instance: BaseModelType | None
    def __init__(
        self,
        *,
        owner: type[BaseModelType] | None = ...,
        inherit: bool = ...,
        name: str = ...,
        instance: BaseModelType | None = ...,
    ) -> None: ...
    @property
    def model_class(self) -> Any: ...
    def get_queryset(self) -> QuerySet: ...
    def __getattr__(self, name: str) -> Any: ...

class Manager(BaseManager): ...

class RedirectManager(BaseManager):
    redirect_name: str
    def __init__(self, *, redirect_name: str, **kwargs: Any) -> None: ...
