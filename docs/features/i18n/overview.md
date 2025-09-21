# Internationalization

FastEdgy provides a complete internationalization system based on Babel, supporting multiple languages with automatic locale detection and translation management.

## Key features

- **Babel-based**: Uses industry-standard .po files for translations
- **Automatic locale detection**: Detects user language from Accept-Language header
- **Multi-source support**: Load translations from multiple packages and directories
- **Lazy translation**: Strings are translated at render time, not definition time
- **CLI integration**: Extract and manage translatable strings via CLI
- **Parameter substitution**: Support for dynamic values in translations
- **Fallback system**: Graceful degradation to fallback locale or original text

## How it works

The system automatically detects the user's preferred language from HTTP headers, loads the appropriate translation catalog, and translates strings on-demand using the `_t()` function.

## Translation functions

- **`_t(message, **kwargs)`**: Main translation function with parameter support
- **`_(message, **kwargs)`**: Shorthand alias for `_t()`
- **`TranslatableString`**: Lazy translation object that renders when converted to string

## Locale detection

FastEdgy automatically determines the user's locale by:

1. Parsing the Accept-Language HTTP header
2. Matching against available locales
3. Falling back to configured default locale

## File structure

```
project/
├── translations/
│   ├── en.po       # English translations
│   ├── fr.po       # French translations
│   └── es.po       # Spanish translations
└── app/
    └── models.py   # Code with _t() calls
```

## Use cases

- **Multi-language web applications**: Serve content in user's preferred language
- **API internationalization**: Translate error messages and responses
- **Admin interfaces**: Localize backend interfaces for global teams
- **Email templates**: Send emails in recipient's language

[Usage Guide](guide.md){ .md-button .md-button--primary }
