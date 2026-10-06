# Authentication

FastEdgy provides a built-in JWT-based authentication system with user registration, login, password reset, and route protection.

## Key features

- **JWT tokens**: Access and refresh token support
- **Password hashing**: argon2id, with older bcrypt hashes upgraded at their next login
- **Password policy**: an optional minimum length, checked on registration, reset and change
- **Session revocation**: optionally, changing or resetting a password ends the sessions opened before
- **Route protection**: Dependency injection for protected endpoints
- **User registration**: Simple registration with email validation
- **Password reset**: Email-based password recovery
- **Token refresh**: Automatic token renewal

## Basic usage

```python
from fastedgy.depends.security import get_current_user
from fastedgy.models.user import BaseUser


@app.get("/protected")
async def protected_route(current_user: BaseUser = Depends(get_current_user)):
    return {"user": current_user.email}
```

## Configuration

Set these environment variables:

```env
AUTH_SECRET_KEY=your-secret-key-here
AUTH_ALGORITHM=HS256
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=15
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=30
```

The password policy and the session revocation are off by default (`AUTH_PASSWORD_MIN_LENGTH=0`, `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=false`). Turn them on with:

```env
AUTH_PASSWORD_MIN_LENGTH=8
AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true
```

Read [what to do before turning on the revocation](guide.md#sessions-end-with-a-password-change) first.

## Built-in endpoints

FastEdgy provides ready-to-use authentication endpoints:

- `POST /auth/token` - Login with email/password
- `POST /auth/refresh` - Refresh access token
- `POST /auth/register` - Create new user account
- `POST /auth/password/forgot` - Request password reset
- `POST /auth/password/validate` - Check a reset token
- `POST /auth/password/reset` - Reset password with token
- `POST /auth/password/change` - Change the password of the signed-in account

## User model

Extend the base user model for your needs:

```python
from fastedgy.models.user import BaseUser
from fastedgy.orm import fields


class User(BaseUser):
    # BaseUser provides: id, name, email, password
    phone = fields.CharField(max_length=20, null=True)
    is_active = fields.BooleanField(default=True)

    class Meta:
        tablename = "users"
```

## Token structure

- **Access token**: Short-lived (15 min default), for API access
- **Refresh token**: Long-lived (30 days default), for token renewal
- **JWT payload**: Contains user email and token type, and with `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true` a fingerprint of the password hash, which a password change or reset invalidates

## Use cases

- **API protection**: Secure endpoints with user authentication
- **User management**: Registration, login, profile management
- **Mobile apps**: JWT tokens work perfectly with mobile clients
- **Web apps**: Session-based authentication with token refresh

## Get started

Ready to secure your application? Learn how to implement authentication:

[Usage Guide](guide.md){ .md-button .md-button--primary }
