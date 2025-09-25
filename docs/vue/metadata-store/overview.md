# Metadata Store

**Simple Pinia store for accessing FastEdgy dataset metadata**

The Metadata Store is a Pinia store that fetches and caches metadata from FastEdgy's `/dataset/metadatas` endpoint. It provides a centralized way to access model schemas and field definitions.

## Key Features

- **Centralized Store**: Pinia store for metadata management
- **Lazy Loading**: Fetches metadata only when first accessed
- **Caching**: Stores metadata to avoid repeated API calls
- **Authentication Aware**: Only fetches when user is authenticated

## API Methods

- `fetchMetadatas()`: Force fetch metadata from API
- `getMetadatas()`: Get all metadata (fetches if not cached)
- `getMetadata(modelName)`: Get metadata for specific model
- `loading`: Loading state
- `error`: Error state

## Quick Example

```javascript
import { useMetadataStore } from 'vue-fastedgy'

const metadataStore = useMetadataStore()

// Get all metadata
const allMetadata = await metadataStore.getMetadatas()
console.log(allMetadata) // { User: {...}, Post: {...}, ... }

// Get specific model metadata
const userMetadata = await metadataStore.getMetadata('User')
console.log(userMetadata) // { fields: {...}, relations: {...}, ... }

// Check loading state
console.log(metadataStore.loading) // true/false

// Handle errors
if (metadataStore.error) {
  console.error('Failed to load metadata:', metadataStore.error)
}
```

## Get Started

Ready to use metadata in your application? Check out our guides:

[User Guide](guide.md){ .md-button .md-button--primary }
[Examples & Ideas](examples.md){ .md-button }
