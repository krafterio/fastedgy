# API Routes Generator - Advanced Usage

This guide covers advanced customization for complex use cases.

## Custom Actions

Create custom endpoints beyond standard CRUD operations:

```python
from fastedgy.api_route_model.actions import BaseApiRouteAction
from fastapi import APIRouter, HTTPException

class ActivateApiRouteAction(BaseApiRouteAction):
    name = "activate"

    @classmethod
    def register_route(cls, router, model_cls, options):
        async def activate_item(item_id: int, active: bool = True):
            item = await model_cls.objects.get(id=item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")

            item.is_active = active
            await item.update()
            return item

        router.add_api_route(
            path=f"/{item_id}/activate",
            endpoint=activate_item,
            methods=["POST"],
            **options
        )

# Register and use
from fastedgy.dependencies import get_service
from fastedgy.api_route_model.actions import ApiRouteActionRegistry

arar = get_service(ApiRouteActionRegistry)
arar.register_action(ActivateApiRouteAction)

@api_route_model(activate=True)
class Product(Model):
    name = fields.CharField(max_length=200)
    is_active = fields.BooleanField(default=True)
```

## View Transformers

FastEdgy provides a comprehensive View Transformers system for customizing data at different stages of the request lifecycle.

For complete documentation including all transformer types, registration patterns, and advanced examples, see the dedicated **[View Transformers](../view-transformers/overview.md)** section.

## Route Customization

Customize generated endpoints:

```python
@api_route_model(
    list={
        "path": "/all-products",
        "summary": "Get all products",
        "dependencies": [Depends(rate_limit)],
    },
    create={
        "dependencies": [Depends(admin_required)],
        "status_code": 201,
    },
    delete={
        "dependencies": [Depends(super_admin_required)],
    },
    export=False  # Disable export endpoint
)
class Product(Model):
    name = fields.CharField(max_length=200)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
```

## Admin Routes

Separate admin endpoints with different permissions:

```python
from fastedgy.api_route_model import admin_api_route_model

@admin_api_route_model()
class AdminUser(Model):
    username = fields.CharField(max_length=150)
    is_staff = fields.BooleanField(default=False)

# Register separately
from fastedgy.api_route_model.router import register_admin_api_route_models

admin_router = APIRouter(prefix="/admin/api", dependencies=[Depends(admin_required)])
register_admin_api_route_models(admin_router)
app.include_router(admin_router)
```

[Back to Overview](overview.md){ .md-button }
