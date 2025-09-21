# Storage - Usage guide

This guide shows you how to use the Storage service in your FastEdgy application.

## Configuration

Set the storage path in your environment file (`.env`):

```env
DATA_PATH=./storage
```

## File organization

Files are organized based on the `directory_path` you provide in your upload calls:

- **Workspace storage** (`global_storage=False`): `{DATA_PATH}/{workspace_id}/{directory_path}/`
- **Global storage** (`global_storage=True`): `{DATA_PATH}/{directory_path}/`

Example with `DATA_PATH=./storage`:
```
storage/
├── 123/                # workspace_id=123 files
│   ├── photos/         # directory_path="photos"
│   │   └── image.jpg
│   └── avatars/        # directory_path="avatars"
│       └── avatar.png
├── 456/                # workspace_id=456 files
│   └── documents/      # directory_path="documents"
│       └── file.pdf
├── media/              # global_storage=True, directory_path="media"
│   └── shared.jpg
└── public/             # global_storage=True, directory_path="public"
    └── logo.png
```

## File upload

### Basic upload

```python
from fastedgy.app import FastEdgy
from fastedgy.dependencies import Inject
from fastedgy.storage import Storage
from fastapi import UploadFile, File

app = FastEdgy()

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    directory: str = "photos",
    storage: Storage = Inject(Storage)
):
    # Upload to workspace-specific directory
    file_path = await storage.upload(
        file=file,
        directory_path=directory
    )
    return {"path": file_path, "filename": file.filename}
```

### Upload with custom filename

```python
@app.post("/upload-avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    storage: Storage = Inject(Storage)
):
    file_path = await storage.upload(
        file=file,
        directory_path="avatars",
        filename="avatar.{ext}"  # {ext} is replaced with file extension
    )
    return {"avatar_path": file_path}
```

### Global storage

```python
@app.post("/upload-global")
async def upload_global(
    file: UploadFile = File(...),
    directory: str = "shared",
    storage: Storage = Inject(Storage)
):
    # Upload to global directory (shared across workspaces)
    file_path = await storage.upload(
        file=file,
        directory_path=directory,
        global_storage=True
    )
    return {"path": file_path}
```

## Model field upload

Use the built-in API endpoints to upload directly to model fields:

```python
from fastedgy.orm import Model, fields
from fastedgy.api_route_model import api_route_model

@api_route_model()
class User(Model):
    name = fields.CharField(max_length=100)
    avatar = fields.CharField(max_length=255, null=True)

    class Meta:
        tablename = "users"
```

Upload to the model field:
```bash
# Upload avatar for user ID 123
POST /storage/upload/user/123/avatar
Content-Type: multipart/form-data

file: [image file]
```

## Download files

The built-in endpoint handles file serving:

```bash
# Download file
GET /storage/download/photos/image.jpg

# Force download (with Content-Disposition header)
GET /storage/download/photos/image.jpg?force_download=true
```

## Upload from URL

```python
@app.post("/upload-from-url")
async def upload_from_url(
    url: str,
    directory: str = "external",
    storage: Storage = Inject(Storage)
):
    file_path = await storage.download_and_upload(
        file_url=url,
        directory_path=directory
    )
    return {"path": file_path}
```

## Upload from base64

```python
@app.post("/upload-base64")
async def upload_base64(
    data: str,  # base64-encoded image
    directory: str = "images",
    storage: Storage = Inject(Storage)
):
    file_path = await storage.upload_from_base64(
        data=data,
        directory_path=directory
    )
    return {"path": file_path}
```

## Error handling

The Storage service validates files automatically:

- **File type**: Only images are accepted
- **Extensions**: JPG, JPEG, PNG, GIF, WEBP
- **Filename**: Must be provided

```python
@app.post("/safe-upload")
async def safe_upload(
    file: UploadFile = File(...),
    directory: str = "files",
    storage: Storage = Inject(Storage)
):
    try:
        file_path = await storage.upload(
            file=file,
            directory_path=directory
        )
        return {"success": True, "path": file_path}
    except ValueError as e:
        return {"success": False, "error": str(e)}
```

[Back to Overview](overview.md){ .md-button }
