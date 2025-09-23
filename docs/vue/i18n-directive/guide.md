# I18n Directive Basic Usage

This guide shows you how to use the `v-tc` directive **responsibly** as a complementary tool to vue-i18n for specific use cases involving multi-line content translations.

!!! important "Complementary Tool"
    The `v-tc` directive is designed to **complement**, not replace, vue-i18n best practices. Use it judiciously for cases where it genuinely improves template readability, particularly with multi-line content.

## Global Text Translation Examples

The `v-tc` directive is particularly useful for translating complete text content directly in your templates. Instead of using translation keys, you can write the full text content within the element:

```vue
<template>
  <div class="terms-and-conditions">
    <!-- Complete text with parameters -->
    <p v-tc="{ company: 'Acme Corporation', effectiveDate: '2024-01-01' }">
      By using our services, you agree to be bound by these Terms of Service.
      These terms are effective as of {effectiveDate} and apply to all users of
      {company}'s platform and services.
    </p>

    <!-- Long help instruction -->
    <div class="setup-instructions" v-tc="{ version: '2.1.0', supportEmail: 'support@example.com' }">
      To complete the setup process, please download version {version} of our application
      and follow the installation wizard. If you encounter any issues during installation,
      please contact our support team at {supportEmail} for assistance.
    </div>

    <!-- Multi-paragraph content -->
    <section class="privacy-notice">
      <div v-tc="{ dataRetention: '90 days', region: 'European Union' }">
        We collect and process your personal data in accordance with applicable privacy laws.
        Your data is stored securely in the {region} and retained for a maximum of {dataRetention}
        unless required by law to be kept longer. You have the right to request deletion of your
        personal information at any time.
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// These values can be reactive and come from your application state
const company = ref('Acme Corporation')
const effectiveDate = ref('2024-01-01')
const version = ref('2.1.0')
const supportEmail = ref('support@example.com')
const dataRetention = ref('90 days')
const region = ref('European Union')
</script>
```

This approach is ideal when:

- You have long, descriptive text content
- The text must be splitted in multiple lines
- The text contains multiple sentences or paragraphs
- Using `{{ $t() }}` would make your template cluttered and hard to read
- You need to include dynamic parameters within flowing text

## Summary

The `v-tc` directive is a **specialized tool** for specific use cases:

- **Use for**: Multi-line content, complex paragraphs, detailed explanations
- **Don't use for**: Simple labels, titles, buttons, short text
- **Remember**: It complements vue-i18n, it doesn't replace it

**Golden Rule**: If your translation content is more than one line or contains complex formatting, consider `v-tc`. For everything else, stick with `{{ $t() }}`.
