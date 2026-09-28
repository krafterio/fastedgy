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
        raise HTTPException(status_code=404, detail=str(_t("User {id} not found", id=user_id)))
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
Configure the languages your application offers in your settings:

```python
class Settings(BaseSettings):
    available_locales: list[str] = ["fr", "en", "es"]
    fallback_locale: str = "en"
    source_locale: str = "fr"
```

- `available_locales`: the languages offered, matched against the `Accept-Language` header.
- `fallback_locale`: the language of a request that asks for none of them, and where a missing translation is looked up next.
- `source_locale`: the language the messages are written in, `fallback_locale` when not set.

A message is looked up in the locale of the request, then in the fallback locale, then returned as written. The source locale skips the fallback: its messages are already the text to show.

The messages of fastedgy itself keep their own source language, English. A message belongs to the application when its catalogs translate it, and to a package otherwise, so an application can write its messages in another language than the one of the framework.

A package written in another language than English declares its source language, by package name, and its `translations` directory is read along:

```python
class Settings(BaseSettings):
    package_source_locales: dict[str, str] = {"mypackage": "de"}
```

The Vue.js and Flutter clients take the same options, under the names `availableLocales`, `fallbackLocale` and `sourceLocale`.

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
