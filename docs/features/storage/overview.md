# Storage

FastEdgy provides a built-in Storage service for handling file uploads, downloads, and management. It supports workspace-based file isolation and integrates seamlessly with your models.

## Key features

- **File uploads**: Upload images via API endpoints
- **Workspace isolation**: Files are automatically organized by workspace
- **Model integration**: Direct upload to model fields
- **Multiple formats**: Support for UploadFile, base64, and URL downloads
- **REST API**: Built-in endpoints for upload/download/delete operations
- **Image validation**: Automatic validation for supported image formats
- **Image optimization**: Automatic resizing, format conversion, and caching

## Supported formats

- **Images**: JPG, JPEG, PNG, GIF, WEBP
- **Upload methods**: File upload, base64 data, URL download

## Basic usage

```python
from fastedgy.dependencies import Inject
from fastedgy.storage import Storage
from fastapi import UploadFile


async def upload_file(file: UploadFile, directory: str, storage: Storage = Inject(Storage)):
    # Upload to specified directory
    file_path = await storage.upload(file=file, directory_path=directory)
    return {"path": file_path}
```

## Image optimization

FastEdgy includes automatic image optimization with URL parameters. Transform, resize, and convert images on-the-fly with intelligent caching.

- **On-demand processing**: Add URL parameters to resize or convert images
- **Smart caching**: Optimized images are cached for better performance
- **Modern formats**: Convert to WebP for smaller file sizes
- **Responsive ready**: Perfect for mobile and desktop layouts

[Learn more about Image Optimization →](image-optimization.md)

## Configuration

Set the storage path and image quality in your environment file (`.env`):

```env
DATA_PATH=/path/to/storage
IMAGE_QUALITY=80
```

Files are organized based on the `directory_path` you provide:
```
data/
├── {workspace_id}/    # Workspace storage
│   └── {directory_path}/
│       └── file.jpg
└── {directory_path}/  # Global storage (root level)
    └── file.jpg
```

## Built-in API endpoints

The Storage service provides REST endpoints:

- `POST /storage/upload/{model}/{model_id}/{field}` - Upload to model field
- `GET /storage/download/{path}` - Download file
- `DELETE /storage/file/{model}/{model_id}/{field}` - Delete model field file

The two model field routes only write a text field that the model's PATCH route
accepts, and write it through that route: the caller needs the route (the
console one requires sudo), and the model's `PreSaveTransformer` runs. The
request's own user and workspace are the exception, written directly. Another
user or workspace without a PATCH route for the caller is a 404, unless a
`PreUploadTransformer` or `PreDeleteFileTransformer` sets
`ctx["write_allowed"] = True`.

A stored path never contains a `..` part: the storage refuses it.

## Use cases

- **User avatars**: Profile picture uploads
- **Document storage**: File attachments
- **Image galleries**: Product photos, media content
- **Workspace files**: Team-specific file storage

## Get started

Ready to handle file uploads? Learn how to implement the Storage service:

[Usage Guide](guide.md){ .md-button .md-button--primary }
