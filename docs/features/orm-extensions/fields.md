# Fields

All available field types for FastEdgy models, listed alphabetically.

## Big Integer

64-bit integer field for large numbers.

```python
class Analytics(BaseModel):
    class Meta:
        tablename = "analytics"

    total_page_views = fields.BigIntegerField(label=_t('Total page views'))
```

## Binary Data

Field for storing binary data.

```python
class Attachment(BaseModel):
    class Meta:
        tablename = "attachments"

    data = fields.BinaryField(label=_t('File Data'))
```

## Boolean

Boolean field for true/false values.

```python
class UserAccount(BaseModel):
    class Meta:
        tablename = "user_accounts"

    is_account_active = fields.BooleanField(default=True, label=_t('Is Account Active'))
```

## Character Choice

Character-based choice field with predefined string options.

```python
from enum import Enum

class UserRole(str, Enum):
    admin = "admin"
    user = "user"
    guest = "guest"

class User(BaseModel):
    class Meta:
        tablename = "users"

    role = fields.CharChoiceField(choices=UserRole, default=UserRole.user, label=_t('User Role'))
```

## Character

Short text field with maximum length limit.

```python
class User(BaseModel):
    class Meta:
        tablename = "users"

    name = fields.CharField(max_length=100, label=_t('Name'))
```

## Choice

Choice field for predefined options.

```python
from enum import Enum

class OrderStatus(str, Enum):
    pending = "pending"
    shipped = "shipped"
    delivered = "delivered"

class Order(BaseModel):
    class Meta:
        tablename = "orders"

    status = fields.ChoiceField(choices=OrderStatus, default=OrderStatus.pending, label=_t('Status'))
```

## Composite

Composite field for combining multiple fields into one.

```python
class Location(BaseModel):
    class Meta:
        tablename = "locations"

    coordinates = fields.CompositeField(label=_t('Coordinates'))
```

## Computed

Computed field for database-computed values.

```python
class Order(BaseModel):
    class Meta:
        tablename = "orders"

    total = fields.ComputedField(label=_t('Total Amount'))
```

## Date

Date field for storing dates (year, month, day).

```python
class Event(BaseModel):
    class Meta:
        tablename = "events"

    event_date = fields.DateField(label=_t('Event Date'))
```

## Date Time

DateTime field for storing date and time with timezone support.

```python
class Post(BaseModel):
    class Meta:
        tablename = "posts"

    created_at = fields.DateTimeField(auto_now_add=True, label=_t('Created At'))
```

## Decimal

Fixed-precision decimal field for exact calculations.

```python
class Product(BaseModel):
    class Meta:
        tablename = "products"

    price = fields.DecimalField(max_digits=10, decimal_places=2, label=_t('Price'))
```

## Duration

Field for storing time duration/intervals.

```python
class Task(BaseModel):
    class Meta:
        tablename = "tasks"

    estimated_duration = fields.DurationField(label=_t('Estimated Duration'))
```

## Email

Email field with automatic email validation.

```python
class User(BaseModel):
    class Meta:
        tablename = "users"

    email = fields.EmailField(label=_t('Email Address'))
```

## Exclude

Field that is excluded from certain operations.

```python
class InternalModel(BaseModel):
    class Meta:
        tablename = "internal_models"

    internal_data = fields.ExcludeField(label=_t('Internal Data'))
```

## File

File field for storing file references.

```python
class Document(BaseModel):
    class Meta:
        tablename = "documents"

    file = fields.FileField(label=_t('File Path'))
```

## Float

Floating-point number field.

```python
class Measurement(BaseModel):
    class Meta:
        tablename = "measurements"

    temperature = fields.FloatField(label=_t('Temperature'))
```

## Foreign Key

Many-to-one relationship field linking to another model.

```python
class Product(BaseModel):
    class Meta:
        tablename = "products"

    category = fields.ForeignKey("Category", on_delete="CASCADE", label=_t('Category'))
```

## HTML

HTML content field with specialized handling for HTML markup.

```python
class Article(BaseModel):
    class Meta:
        tablename = "articles"

    content = fields.HTMLField(label=_t('HTML Content'))
```

## Image

Image field for storing image file references.

```python
class Product(BaseModel):
    class Meta:
        tablename = "products"

    image = fields.ImageField(label=_t('Image'))
```

## Integer

32-bit integer field.

```python
class Product(BaseModel):
    class Meta:
        tablename = "products"

    quantity = fields.IntegerField(label=_t('Quantity'))
```

## IP Address

IP address field for storing IPv4/IPv6 addresses.

```python
class Connection(BaseModel):
    class Meta:
        tablename = "connections"

    ip_address = fields.IPAddressField(label=_t('IP Address'))
```

## JSON

JSON field for storing structured data.

```python
class Configuration(BaseModel):
    class Meta:
        tablename = "configurations"

    settings = fields.JSONField(label=_t('Settings'))
```

## Many to Many

Many-to-many relationship field for multiple associations.

```python
class Tag(BaseModel):
    class Meta:
        tablename = "tags"

    products = fields.ManyToManyField("Product", related_name="tags", label=_t('Products'))
```

## One to One

One-to-one relationship field for unique associations.

```python
class UserProfile(BaseModel):
    class Meta:
        tablename = "user_profiles"

    user = fields.OneToOneField("User", on_delete="CASCADE", label=_t('User'))
```

## Password

Password field with automatic hashing.

```python
class User(BaseModel):
    class Meta:
        tablename = "users"

    password = fields.PasswordField(label=_t('Password'))
```

## PostgreSQL Array

PostgreSQL array field for storing arrays of values.

```python
class Product(BaseModel):
    class Meta:
        tablename = "products"

    tags = fields.PGArrayField(base_field=fields.CharField(max_length=50), label=_t('Tags'))
```

## Phone

Phone number field with phone number validation.

```python
class Contact(BaseModel):
    class Meta:
        tablename = "contacts"

    phone = fields.PhoneField(label=_t('Phone Number'))
```

## Placeholder

Placeholder field for dynamic field definitions.

```python
class DynamicModel(BaseModel):
    class Meta:
        tablename = "dynamic_models"

    dynamic_field = fields.PlaceholderField(label=_t('Dynamic Field'))
```

## Reference Foreign Key

Foreign key with additional reference capabilities.

```python
class Comment(BaseModel):
    class Meta:
        tablename = "comments"

    author = fields.RefForeignKey("User", on_delete="CASCADE", label=_t('Author'))
```

## Small Integer

16-bit integer field for small numbers.

```python
class Settings(BaseModel):
    class Meta:
        tablename = "settings"

    priority = fields.SmallIntegerField(label=_t('Priority'))
```

## Text

Large text field for long content without length limit.

```python
class Post(BaseModel):
    class Meta:
        tablename = "posts"

    content = fields.TextField(label=_t('Content'))
```

## Time

Time field for storing time information (hours, minutes, seconds).

```python
class Schedule(BaseModel):
    class Meta:
        tablename = "schedules"

    start_time = fields.TimeField(label=_t('Start Time'))
```

## URL

URL field with automatic URL validation.

```python
class Website(BaseModel):
    class Meta:
        tablename = "websites"

    url = fields.URLField(label=_t('Website URL'))
```

## UUID

UUID field for storing universally unique identifiers.

```python
class Token(BaseModel):
    class Meta:
        tablename = "tokens"

    uuid = fields.UUIDField(label=_t('Unique ID'))
```

## Vector

Vector field for AI embeddings and similarity search.

```python
class Document(BaseModel):
    class Meta:
        tablename = "documents"

    embedding = fields.VectorField(dimensions=1536, label=_t('AI Embedding'))
```
