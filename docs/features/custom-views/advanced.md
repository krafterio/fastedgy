# Custom views - Advanced usage

## Your own model

An application declares its own model by subclassing `BaseCustomView` before the application is
built; FastEdgy then stands down and keeps every rule of the feature. A subclass declares its
workspace key itself, towards the application's workspace model:

```python
from fastedgy import context
from fastedgy.api_route_model import api_route_model
from fastedgy.api_route_model.decorators import console_api_route_model
from fastedgy.models.custom_view import BaseCustomView
from fastedgy.orm import fields
from fastedgy.realtime import realtime_model


@realtime_model()
@console_api_route_model()
@api_route_model()
class CustomView(BaseCustomView):
    class Meta(BaseCustomView.Meta):
        tablename = "custom_views"
        indexes = [
            fields.Index(fields=["workspace", "model", "scope", "sequence"], suffix="idx_custom_views"),
            fields.Index(fields=["user"], suffix="idx_custom_views"),
        ]

    workspace = fields.ForeignKey(
        "Household", null=True, on_delete="CASCADE", related_name=False, exclude=True
    )

    @classmethod
    def can_manage_shared(cls) -> bool:
        membership = context.get_workspace_user()

        return membership is None or getattr(membership, "role", None) == "admin"
```

## Who manages the shared views

`can_manage_shared()` is true by default: whoever sees a shared view may change it. The override
above keeps the shared views of a workspace to its administrators, while every member saves private
views and chooses a favorite. Saving or deleting a shared view the current user does not manage
answers 403, and `editable` tells the client what to offer.

## Your own favorite model

`BaseCustomViewFavorite` is subclassed the same way, with its `view` key towards the custom view
model, `related_name="favorites"` so the opening request reads it.
