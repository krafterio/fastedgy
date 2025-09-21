# Internationalization - Usage guide

## Basic usage

### Mark strings for translation
```python
from fastedgy import _t, _

# Simple translation
message = _t("Hello world")

# With parameters
greeting = _t("Hello {name}", name="John")

# Using shorthand
error = _("User not found")
```

### In Pydantic models
```python
from pydantic import BaseModel
from fastedgy import _t

class ErrorResponse(BaseModel):
    message: str = _t("An error occurred")
    details: str = _t("Please try again later")
```

### In FastAPI endpoints
```python
from fastapi import HTTPException
from fastedgy import _t

async def get_user(user_id: int):
    if not user:
        raise HTTPException(
            status_code=404,
            detail=str(_t("User {id} not found", id=user_id))
        )
```

## CLI commands

### Extract translatable strings
```bash
# Extract for all locales
fastedgy trans extract

# Extract for specific locale
fastedgy trans extract fr

# Extract for specific package
fastedgy trans extract --package mypackage
```

### Initialize new locale
```bash
# Create new translation file
fastedgy trans init en
fastedgy trans init fr --package mypackage
```

## Translation workflow

### 1. Mark strings in code
Add `_t()` calls around user-facing strings throughout your application.

### 2. Extract strings
Run the extract command to scan your code and create/update .po files with found strings.

### 3. Translate strings
Edit the .po files to add translations for each language.

### 4. Test translations
Start your application and test with different Accept-Language headers or locale settings.

## Configuration

### Available locales
Configure supported languages in your settings:

```python
class Settings(BaseSettings):
    available_locales: list[str] = ["en", "fr", "es"]
    fallback_locale: str = "en"
```

### Translation directories
Specify where translation files are located:

```python
class Settings(BaseSettings):
    translations_paths: list[str] = ["translations/"]
```

## Advanced patterns

### Lazy translation in models
```python
from fastedgy.orm import Model, fields
from fastedgy import _t

class Category(Model):
    name = fields.CharField(max_length=100)

    @property
    def display_name(self):
        return str(_t("category.{slug}", slug=self.slug))
```

### Context-aware translations
```python
def get_status_message(status: str, count: int):
    if count == 1:
        return _t("status.{status}.singular", status=status)
    else:
        return _t("status.{status}.plural", status=status, count=count)
```

### Template translations
```python
from fastedgy import _t

# Email template
subject = _t("Welcome {name}!", name=user.name)
body = _t("Thanks for joining {site_name}.", site_name="MyApp")
```

## File format

Translation files use standard .po format:

```po
# translations/fr.po
msgid "Hello world"
msgstr "Bonjour le monde"

msgid "Hello {name}"
msgstr "Bonjour {name}"

msgid "User not found"
msgstr "Utilisateur introuvable"
```

## Testing translations

### Set locale for testing
```python
from fastedgy.context import set_locale

# In tests
set_locale("fr")
assert str(_t("Hello world")) == "Bonjour le monde"
```

### HTTP headers
```bash
curl -H "Accept-Language: fr-FR,fr;q=0.9" http://localhost:8000/api/users
```

[Back to Overview](overview.md){ .md-button }
