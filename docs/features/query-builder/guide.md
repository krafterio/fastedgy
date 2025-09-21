# Query Builder - Usage guide

## All available operators

### General operators

| Operator | Description |
|----------|-------------|
| `=` | Equal to |
| `!=` | Not equal to |
| `<` | Less than |
| `<=` | Less than or equal |
| `>` | Greater than |
| `>=` | Greater than or equal |
| `between` | Between two values |
| `like` | SQL LIKE pattern matching |
| `ilike` | SQL LIKE pattern matching (case insensitive) |
| `not like` | SQL NOT LIKE pattern matching |
| `not ilike` | SQL NOT LIKE pattern matching (case insensitive) |
| `starts with` | Starts with text |
| `ends with` | Ends with text |
| `not starts with` | Does not start with text |
| `not ends with` | Does not end with text |
| `contains` | Contains text (case sensitive) |
| `icontains` | Contains text (case insensitive) |
| `not contains` | Does not contain text (case sensitive) |
| `not icontains` | Does not contain text (case insensitive) |
| `match` | Full-text search match |
| `in` | Value is in list |
| `not in` | Value is not in list |
| `is true` | Boolean field is true |
| `is false` | Boolean field is false |
| `is empty` | Field is null or empty |
| `is not empty` | Field has a value |

### Vector field operators

| Operator | Description |
|----------|-------------|
| `l1 distance` | L1/Manhattan distance |
| `l1 distance <` | L1 distance less than |
| `l1 distance <=` | L1 distance less than or equal |
| `l1 distance >` | L1 distance greater than |
| `l1 distance >=` | L1 distance greater than or equal |
| `l2 distance` | L2/Euclidean distance |
| `l2 distance <` | L2 distance less than |
| `l2 distance <=` | L2 distance less than or equal |
| `l2 distance >` | L2 distance greater than |
| `l2 distance >=` | L2 distance greater than or equal |
| `cosine distance` | Cosine distance |
| `cosine distance <` | Cosine distance less than |
| `cosine distance <=` | Cosine distance less than or equal |
| `cosine distance >` | Cosine distance greater than |
| `cosine distance >=` | Cosine distance greater than or equal |
| `inner product` | Inner product |
| `inner product <` | Inner product less than |
| `inner product <=` | Inner product less than or equal |
| `inner product >` | Inner product greater than |
| `inner product >=` | Inner product greater than or equal |

## Filter syntax

```bash
# Simple rule: ["field", "operator", "value"]
GET /api/products/
X-Filter: ["name", "=", "Laptop"]

# AND conditions: ["&", [rule1, rule2, ...]]
GET /api/products/
X-Filter: ["&", [["price", ">=", 100], ["is_active", "is true"]]]

# OR conditions: ["|", [rule1, rule2, ...]]
GET /api/products/
X-Filter: ["|", [["category", "=", "electronics"], ["category", "=", "books"]]]
```

## Available operators

### CharField, TextField
**Operators**: `=`, `!=`, `like`, `ilike`, `not like`, `not ilike`, `starts with`, `ends with`, `not starts with`, `not ends with`, `contains`, `icontains`, `not contains`, `not icontains`, `match`, `in`, `not in`, `is empty`, `is not empty`

**Example**:
```bash
GET /api/products/
X-Filter: ["description", "icontains", "smartphone"]
```

### IntegerField, FloatField, DecimalField
**Operators**: `=`, `!=`, `<`, `<=`, `>`, `>=`, `between`, `in`, `not in`, `is empty`, `is not empty`

**Example**:
```bash
GET /api/products/
X-Filter: ["price", "between", [100, 500]]
```

### BooleanField
**Operators**: `is true`, `is false`

**Example**:
```bash
GET /api/products/
X-Filter: ["is_featured", "is true"]
```

### DateField, DateTimeField
**Operators**: `=`, `!=`, `<`, `<=`, `>`, `>=`, `between`, `is empty`, `is not empty`

**Example**:
```bash
GET /api/orders/
X-Filter: ["created_at", ">=", "2024-01-01T00:00:00Z"]
```

### ChoiceField
**Operators**: `=`, `!=`, `in`, `not in`, `is empty`, `is not empty`

**Example**:
```bash
GET /api/orders/
X-Filter: ["status", "in", ["pending", "processing"]]
```

### ForeignKey, OneToOne
**Operators**: `=`, `!=`, `in`, `not in`, `is empty`, `is not empty`

**Example**:
```bash
GET /api/products/
X-Filter: ["category.name", "=", "Electronics"]
```

### ManyToMany
**Operators**: `in`, `not in`, `is empty`, `is not empty`

**Example**:
```bash
GET /api/products/
X-Filter: ["tags", "not in", [1, 2, 3]]
```

### UUIDField
**Operators**: `=`, `!=`, `like`, `ilike`, `not like`, `not ilike`, `starts with`, `ends with`, `not starts with`, `not ends with`, `contains`, `icontains`, `not contains`, `not icontains`, `match`, `in`, `not in`, `is empty`, `is not empty`

**Example**:
```bash
GET /api/users/
X-Filter: ["uuid", "starts with", "550e8400"]
```

### VectorField
**Operators**: `l1 distance`, `l1 distance <`, `l1 distance <=`, `l1 distance >`, `l1 distance >=`, `l2 distance`, `l2 distance <`, `l2 distance <=`, `l2 distance >`, `l2 distance >=`, `cosine distance`, `cosine distance <`, `cosine distance <=`, `cosine distance >`, `cosine distance >=`, `inner product`, `inner product <`, `inner product <=`, `inner product >`, `inner product >=`

**Example**:
```bash
GET /api/embeddings/
X-Filter: ["vector", "cosine distance <", [0.1, [0.2, 0.3, 0.4]]]
```

## Complex filtering

```bash
# Nested AND/OR
GET /api/products/
X-Filter: ["&", [
  ["is_active", "is true"],
  ["|", [["price", "<", 50], ["category.slug", "=", "sale"]]]
]]
```

## Error responses

- **422**: Invalid field, operator, or JSON format
- **422**: Type conversion errors

[Back to Overview](overview.md){ .md-button }
