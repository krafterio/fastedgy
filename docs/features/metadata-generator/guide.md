# Metadata Generator - Usage guide

## Model registration

### Automatic registration
Models with `@api_route_model()` decorator are automatically registered for metadata generation.

### Manual registration
Use `@metadata_model()` decorator to register models without API routes.

### Registry control
The MetadataModelRegistry manages which models expose their metadata and when they're processed.

## Metadata structure

### Model metadata
Each registered model generates metadata containing:

- **name**: Snake_case model identifier
- **label**: Human-readable singular name
- **label_plural**: Human-readable plural name
- **searchable**: Whether model has searchable fields
- **fields**: Dictionary of field metadata

### Field metadata
Each model field produces metadata with:

- **name**: Field name
- **label**: Human-readable label
- **type**: Metadata field type (string, integer, boolean, etc.)
- **readonly**: Whether field can be modified
- **required**: Whether field is mandatory
- **searchable**: Whether field can be filtered
- **filter_operators**: Available query operators
- **target**: Related model name for relationships

## Field type mapping

The generator maps ORM field types to standardized metadata types:

- **CharField/TextField** → `string`
- **IntegerField** → `integer`
- **BooleanField** → `boolean`
- **DateTimeField** → `datetime`
- **ForeignKey** → `many2one` and `one2many` if `related_name` is defined
- **ManyToMany** → `many2many`
- **JSONField** → `json`

## Label generation

### Model labels
- **Class name**: `ProductCategory` → `Product Category`
- **Custom labels**: Override via `Meta.label` and `Meta.label_plural`

### Field labels
- **Field name**: `created_at` → `Created at`
- **Custom labels**: Override via field `label` parameter

## API endpoints

### List all metadata
`GET /api/dataset/metadatas` - Returns metadata for all registered models

### Metadata format
Responses follow the `MetadataModel` schema with consistent structure across all models.

## Integration patterns

### Frontend integration
Metadata enables dynamic frontend applications that adapt to model changes without code updates.

### Validation integration
Field metadata provides validation rules for both frontend and backend validation.

### Query builder integration
Filter operators metadata powers dynamic query interfaces.

### Form generation integration
Field metadata contains all information needed for automatic form generation.

[Back to Overview](overview.md){ .md-button }
