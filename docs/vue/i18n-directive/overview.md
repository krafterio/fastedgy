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

Add the i18n extra plugin to your Vue application:

```javascript
import { createI18nExtra } from 'vue-fastedgy/plugins/i18nExtra'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  // your i18n configuration
})

const app = createApp(App)

// Install the i18n extra plugin
app.use(createI18nExtra(i18n))
app.use(i18n)
```

## Get Started

Ready to simplify your translations? Check out our detailed guide:

[Basic Usage](guide.md){ .md-button .md-button--primary }
