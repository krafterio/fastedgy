# Authentication - Usage guide

This guide shows you how to implement authentication in your FastEdgy application.

## Configuration

Set authentication settings in your environment file (`.env`):

```env
AUTH_SECRET_KEY=your-very-long-secret-key-here-at-least-32-chars
AUTH_ALGORITHM=HS256
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=15
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=30
```

## User registration

```python
# User registration happens via the built-in endpoint
# POST /auth/register
{
    "name": "John Doe",
    "email": "john@example.com",
    "password": "secure_password"
}
```

Or create users programmatically:

```python
from fastedgy.depends.security import hash_password
from fastedgy.dependencies import Inject
from fastedgy.orm import Registry

async def create_user(
    name: str,
    email: str,
    password: str,
    registry: Registry = Inject(Registry)
):
    User = registry.get_model("User")

    hashed_password = hash_password(password)
    user = User(
        name=name,
        email=email,
        password=hashed_password
    )
    await user.save()
    return user
```

## User login

```python
# Login via built-in endpoint
# POST /auth/token
{
    "username": "john@example.com",  # Email as username
    "password": "secure_password"
}

# Returns:
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer"
}
```

## Protecting endpoints

```python
from fastedgy.depends.security import get_current_user
from fastedgy.models.user import BaseUser
from fastapi import Depends

@app.get("/profile")
async def get_profile(
    current_user: BaseUser = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email
    }

@app.post("/protected-action")
async def protected_action(
    data: dict,
    current_user: BaseUser = Depends(get_current_user)
):
    # Only authenticated users can access this
    return {"message": f"Hello {current_user.name}", "data": data}
```

## Token refresh

```python
# Refresh access token via built-in endpoint
# POST /auth/refresh
{
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}

# Returns new access token
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer"
}
```

## Using tokens in requests

Include the access token in your API requests:

```bash
# Authorization header
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...

# Example with curl
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     http://localhost:8000/api/profile
```

## Password reset

The built-in endpoints handle password reset flow:

1. **Request reset**: `POST /auth/forgot-password`
2. **Validate token**: `POST /auth/forgot-password/validate`
3. **Reset password**: `POST /auth/reset-password`

```python
# 1. Request password reset
{
    "email": "john@example.com"
}

# 2. User receives email with reset token
# 3. Reset password with token
{
    "token": "reset-token-from-email",
    "password": "new_secure_password"
}
```

## Custom user model

Extend the base user model:

```python
from fastedgy.models.user import BaseUser
from fastedgy.orm import fields
from fastedgy.api_route_model import api_route_model

@api_route_model()
class User(BaseUser):
    phone = fields.CharField(max_length=20, null=True)
    is_verified = fields.BooleanField(default=False)
    created_at = fields.DateTimeField(auto_now_add=True)

    class Meta:
        tablename = "users"
```

## Error handling

Authentication endpoints return standard HTTP errors:

- **400 Bad Request**: Email already registered
- **401 Unauthorized**: Invalid credentials
- **422 Unprocessable Entity**: Invalid request data

```python
try:
    # Your authentication logic
    pass
except HTTPException as e:
    if e.status_code == 401:
        # Handle invalid credentials
        pass
```

[Back to Overview](overview.md){ .md-button }
