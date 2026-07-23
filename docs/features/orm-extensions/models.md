# Models

FastEdgy models are based on [Edgy ORM](https://edgy.dymmond.com/) and provide a powerful, type-safe way to define your database schema and interact with data.

## Basic model definition

```python
from fastedgy.models.base import BaseModel
from fastedgy.orm import fields

class Product(BaseModel):
    name = fields.CharField(max_length=255)
    description = fields.TextField()
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    is_active = fields.BooleanField(default=True)

    class Meta:
        tablename = "products"
```

## Base model features

All FastEdgy models inherit from the base model, which provides:

- **Automatic ID**: Primary key `id` field (auto-increment integer)
- **Query managers**: `.query` for workspace-scoped queries, `.global_query` for all data
- **FastEdgy integration**: Automatic service injection and context management
- **Timestamps**: Optional `created_at` and `updated_at` fields

## Model operations

### Create
```python
product = Product(
    name="Laptop",
    description="High-performance laptop",
    price=999.99
)
await product.save()
```

### Query
```python
# Get by ID
product = await Product.query.get(id=1)

# Filter
products = await Product.query.filter(is_active=True).all()

# Complex queries
expensive_products = await Product.query.filter(
    price__gte=500,
    is_active=True
).order_by("-price").all()
```

### Update
```python
product.price = 899.99
await product.save()

# Bulk update
await Product.query.filter(is_active=False).update(is_active=True)
```

### Delete
```python
await product.delete()

# Bulk delete
await Product.query.filter(price__lt=10).delete()
```

## Relationships between models

```python
class Category(BaseModel):
    name = fields.CharField(max_length=100)

    class Meta:
        tablename = "categories"

class Product(BaseModel):
    name = fields.CharField(max_length=255)
    category = fields.ForeignKey(Category, on_delete="CASCADE")
    tags = fields.ManyToMany("Tag", related_name="products")

    class Meta:
        tablename = "products"

class Tag(BaseModel):
    name = fields.CharField(max_length=50)

    class Meta:
        tablename = "tags"
```

## Model configuration

```python
class Product(BaseModel):
    name = fields.CharField(max_length=255)

    class Meta:
        tablename = "products"
        # Optional configurations
        abstract = False  # True for abstract base models
        registry = None   # Auto-set by FastEdgy

        # Database table options
        indexes = [
            fields.Index(fields=["name"]),
        ]
        constraints = [
            fields.UniqueConstraint(fields=["name"], name="unique_product_name")
        ]
```

## Read-only fields

Mark a field `read_only=True` when it must never be set from an API input — a platform role, an immutable owner, a value derived server-side:

```python
class WorkspaceUser(BaseModel):
    workspace = fields.ForeignKey(Workspace, read_only=True)
    user = fields.ForeignKey(User, read_only=True)
    role = fields.CharChoiceField(choices=Role, default=Role.member)
```

Read-only fields are excluded from the generated input schemas, so no `POST`, `PATCH` or [sync](../offline-sync/overview.md) payload can write them. Edgy also drops them on **every** write path — including `Model(field=...)` at construction, attribute assignment before `save()`, and `save(values={...})`. This makes them safe by default, but it also means server code cannot set them the usual way.

### Setting read-only fields from code

Use `apply_readonly_values(...)`, the explicit code-side escape hatch on `BaseModel`. It stages the values and the next `save()` persists them:

```python
membership = WorkspaceUser().apply_readonly_values(
    {"workspace": workspace, "user": user}
)
membership.role = Role.admin
await membership.save()
```

- The staged values also apply to the in-memory instance immediately (so `membership.workspace` reads back).
- They are consumed by the next `save()` and then cleared — call it again for a later write.
- An unknown field name raises `ValueError`.

This keeps the field immutable at the API boundary while leaving it fully writable from trusted code (creation factories, CLI commands, data seeding).

## Automatic API integration

Integrate with FastEdgy's API route generator:

```python
from fastedgy.api_route_model import api_route_model

@api_route_model()
class Product(BaseModel):
    name = fields.CharField(max_length=255)
    price = fields.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        tablename = "products"

# Automatically generates:
# GET    /api/products/     - List products
# POST   /api/products/     - Create product
# GET    /api/products/{id} - Get product
# PATCH  /api/products/{id} - Update product
# DELETE /api/products/{id} - Delete product
```

## Advanced capabilities

- **Signals**: Pre/post save, delete hooks (see Edgy documentation)
- **Custom managers**: Define custom query managers
- **Model inheritance**: Abstract base models and multi-table inheritance
- **Database functions**: Use SQL functions in queries
- **Raw SQL**: Execute custom SQL when needed

## Best practices

- Use descriptive model and field names
- Add appropriate constraints and indexes
- Keep models focused (single responsibility)
- Use relationships to normalize data
- Leverage base model features for consistency

For more advanced ORM features, see the [Edgy ORM documentation](https://edgy.dymmond.com/).
