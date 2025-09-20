# Fetcher Directive

**Authenticated image loading with lazy loading support**

The `v-fetcher-src` directive enables secure image loading through the authenticated fetcher, with support for lazy loading and automatic cleanup. It's specifically designed for loading images that require authentication or need to go through the fetcher pipeline.

## Key Features

- **Authenticated Image Loading**: Load images through the authenticated fetcher
- **Lazy Loading**: Load images only when they enter the viewport
- **Automatic Cleanup**: Properly clean up blob URLs and abort requests
- **Intersection Observer**: Efficient viewport detection for lazy loading
- **Error Handling**: Built-in error handling for failed image loads

## Common Use Cases

- **Protected Images**: Load user avatars, private files, or authenticated content
- **Performance Optimization**: Lazy load images below the fold
- **Blob URL Management**: Automatic creation and cleanup of blob URLs
- **Authenticated Assets**: Load images through the same auth pipeline as API calls

## Basic Usage

```vue
<template>
  <div>
    <!-- Basic authenticated image loading -->
    <img v-fetcher-src src="/user/avatar/123.jpg" alt="User Avatar" />

    <!-- Lazy loading with v-fetcher-src.lazy -->
    <img
      v-fetcher-src.lazy
      src="/user/documents/report.jpg"
      alt="Report Image"
      style="opacity: 0; transition: opacity 0.3s;"
    />
  </div>
</template>
```

## How It Works

The directive automatically:

1. **Authentication**: Images are loaded through the authenticated fetcher
2. **Blob Creation**: Response is converted to blob and creates object URL
3. **Image Assignment**: Blob URL is assigned to the img src
4. **Cleanup**: Blob URL is automatically revoked after loading or unmount
5. **Lazy Loading**: Uses Intersection Observer when `.lazy` modifier is used

## Get Started

Ready to use authenticated image loading? Check out our detailed guide:

[User Guide](guide.md){ .md-button .md-button--primary }
