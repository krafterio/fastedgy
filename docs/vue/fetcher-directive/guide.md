# Fetcher Directive User Guide

This guide shows you how to use the `v-fetcher-src` directive effectively in your Vue.js applications.

## Complete Example

```vue
<template>
  <div>
    <!-- Multiple protected images -->
    <div class="image-gallery">
      <img
        v-for="image in images"
        :key="image.id"
        v-fetcher-src.lazy
        :src="image.url"
        :alt="image.title"
        class="gallery-image"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const images = ref([
  { id: 1, url: '/files/image1.jpg', title: 'Image 1' },
  { id: 2, url: '/files/image2.jpg', title: 'Image 2' },
  { id: 3, url: '/files/image3.jpg', title: 'Image 3' }
])
</script>

<style>
.gallery-image {
  width: 200px;
  height: 150px;
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.3s ease-in-out;
}
</style>
```

## Modifiers

### `.lazy`

Enables lazy loading using Intersection Observer:

```vue
<template>
  <!-- Will only load when the image enters the viewport -->
  <img v-fetcher-src.lazy src="/large-image.jpg" alt="Large Image" />
</template>
```

The lazy modifier provides:
- **Intersection Observer**: Efficient viewport detection
- **Threshold Control**: Images load when 10% visible
- **Automatic Cleanup**: Observer is disconnected after loading

## User Avatar Example

Common pattern for loading authenticated user avatars:

```vue
<template>
  <div class="user-profile">
    <img
      v-fetcher-src
      :src="`/users/${user.id}/avatar`"
      :alt="`${user.name} avatar`"
      class="avatar"
      @error="handleAvatarError"
    />
    <h3>{{ user.name }}</h3>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps(['user'])

const handleAvatarError = () => {
  // Handle case where user has no avatar
  console.log('Avatar failed to load')
}
</script>

<style>
.avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  object-fit: cover;
}
</style>
```

## Document Gallery

Example for loading protected documents/files:

```vue
<template>
  <div class="document-gallery">
    <div
      v-for="document in documents"
      :key="document.id"
      class="document-item"
    >
      <img
        v-fetcher-src.lazy
        :src="`/documents/${document.id}/thumbnail`"
        :alt="document.name"
        class="document-thumbnail"
      />
      <p>{{ document.name }}</p>
    </div>
  </div>
</template>

<script setup>
const documents = ref([
  { id: 1, name: 'Report Q1.pdf' },
  { id: 2, name: 'Invoice 2024.pdf' },
  { id: 3, name: 'Contract.docx' }
])
</script>
```

## Performance Patterns

### Image Grid with Lazy Loading

```vue
<template>
  <div class="image-grid">
    <div
      v-for="item in items"
      :key="item.id"
      class="grid-item"
    >
      <div class="image-container">
        <img
          v-fetcher-src.lazy
          :src="item.imageUrl"
          :alt="item.title"
          class="grid-image"
          loading="lazy"
        />
        <div class="image-overlay">
          <h4>{{ item.title }}</h4>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
}

.image-container {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 8px;
}

.grid-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: opacity 0.3s ease;
}

.image-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(transparent, rgba(0,0,0,0.7));
  color: white;
  padding: 1rem;
}
</style>
```

## Error Handling

```vue
<template>
  <div class="protected-image">
    <img
      v-fetcher-src
      :src="imageUrl"
      :alt="imageAlt"
      class="image"
      @load="handleLoad"
      @error="handleError"
    />

    <div v-if="error" class="error-state">
      <p>Failed to load image</p>
      <button @click="retry">Retry</button>
    </div>

    <div v-if="loading" class="loading-state">
      <p>Loading...</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps(['imageUrl', 'imageAlt'])

const loading = ref(true)
const error = ref(false)

const handleLoad = () => {
  loading.value = false
  error.value = false
}

const handleError = () => {
  loading.value = false
  error.value = true
}

const retry = () => {
  loading.value = true
  error.value = false
  // Force re-render by changing key or src
}
</script>
```

## Technical Details

The directive:
- Uses `useFetcher()` to make authenticated requests
- Converts response to blob for proper image handling
- Creates and manages blob URLs automatically
- Handles component unmount cleanup
- Supports lazy loading with intersection observer
- Automatically aborts requests on component destroy

### Blob URL Management

```javascript
// The directive automatically:
// 1. Creates blob URL: URL.createObjectURL(blob)
// 2. Assigns to img.src
// 3. Revokes on load: URL.revokeObjectURL(url)
// 4. Cleans up on unmount
```

### Intersection Observer Configuration

```javascript
// Default configuration:
new IntersectionObserver(callback, {
  threshold: 0.1  // Trigger when 10% visible
})
```
