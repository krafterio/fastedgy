# I18n Directive

**Complementary tool for multi-line text translations**

FastEdgy for Vue.js uses [vue-i18n](https://vue-i18n.intlify.dev/) as its internationalization solution. The `v-tc` (translate content) directive is a **complementary tool** designed to facilitate the translation of multi-line text content in your Vue.js templates. This directive **does not replace** vue-i18n best practices but provides a convenient alternative for specific use cases where template readability is important.

!!! warning "Best Practices First"
    This directive is a **convenience tool** and should not replace standard vue-i18n practices. Use `{{ $t('key') }}` for most translations and reserve `v-tc` for cases where it genuinely improves template readability, particularly with multi-line content.

## Key Features

- **Multi-line Content**: Ideal for long text content and paragraphs
- **Template Readability**: Reduces template clutter for complex translation keys
- **Parameter Support**: Pass translation parameters as directive values
- **Automatic Reactivity**: Updates automatically when locale changes

## Common Use Cases

- **Long Paragraphs**: Multi-line text content that would clutter templates
- **Complex Translation Keys**: Deeply nested keys that are hard to read inline
- **Content-Heavy Components**: Components with multiple long text sections
- **Template Clarity**: When `{{ $t() }}` expressions would reduce readability

## Installation

Add the i18n extra plugin to your Vue application. It creates vue-i18n and installs it with the `v-tc` directive:

```javascript
import { createApp } from 'vue'
import { createI18nExtra } from 'vue-fastedgy'
import App from './App.vue'

const app = createApp(App)

app.use(createI18nExtra({
  availableLocales: ['fr', 'en', 'es'],
  fallbackLocale: 'en',
  sourceLocale: 'fr',
}))
```

The options are the ones the server and the Flutter client share:

- `availableLocales`: the languages the application offers.
- `locale`: the language the application gives, the account's for instance. Without it, the first language of the browser the application offers, then `fallbackLocale`.
- `fallbackLocale`: the language of whoever speaks none of the others, and where a missing translation is looked up next. The first of `availableLocales` when not given.
- `sourceLocale`: the language the application writes its keys in, `fallbackLocale` when not given.

A key is looked up in the current language, then in the fallback language, then shown as written. The source language skips the fallback: its keys are already the text to show. Any other vue-i18n option, such as `messages`, is passed through.

The words of a package join through `addLocaleMessages(messages, sourceLocale)` and keep their own source language, English unless the package names another. A key belongs to the application when it writes it, and to the package otherwise, so an application can write its keys in another language than the packages it uses.

## Get Started

Ready to simplify your translations? Check out our detailed guide:

[Basic Usage](guide.md){ .md-button .md-button--primary }
