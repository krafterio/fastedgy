# Getting started with custom views

## Prerequisites

- A FastEdgy application with a user model, and a workspace model if the views belong to workspaces.
- The models whose lists get views are registered for metadata (`@api_route_model()` or
  `@metadata_model()`): a view names its list by the metadata name of its model.

## Enable the feature

```python
from fastedgy.app import FastEdgy

app = FastEdgy(custom_views=True)
```

FastEdgy then declares the `CustomView` and `CustomViewFavorite` models, unless the application
declared its own (see [Advanced Usage](advanced.md)). Generate their tables:

```bash
fastedgy db makemigrations -m "add custom views"
fastedgy db migrate
```

## Serve them

The two models carry `@api_route_model()` and `@console_api_route_model()`: they are served wherever
the application registers its generated routes.

```python
from fastedgy.api_route_model.router import register_api_route_models

register_api_route_models(router)
```

## Save and read a view

```bash
POST /api/custom_views
{"name": "Open tickets", "model": "ticket", "filters": ["status", "=", "open"]}

GET /api/custom_views
X-Filter: ["&", [["model", "=", "ticket"], ["scope", "=", ""]]]
```

The second request reads the views of the ticket list, in their menu order.

## What's next

- [User Guide](guide.md): sharing, favorites and the rules a save follows
- [Advanced Usage](advanced.md): your own model
