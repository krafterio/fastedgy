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

Three settings are off by default, so an application that sets none behaves as before they existed. Turn the password policy and the revocation on in the same file:

```env
AUTH_PASSWORD_MIN_LENGTH=8
AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true
```

- `AUTH_PASSWORD_MIN_LENGTH` (default `0`, no minimum): the fewest characters a new password may have, on registration, reset and change.
- `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE` (default `false`): whether a password change or reset ends the sessions opened before, see [Sessions end with a password change](#sessions-end-with-a-password-change).
- `AUTH_PASSWORD_FINGERPRINT_TOKENS` (default `false`): whether tokens carry the password fingerprint the revocation checks, without checking it. An application whose users are already signed in turns it on first, so that turning the revocation on signs nobody out for lack of the claim, see [Turning it on](#turning-it-on).

## User registration

```python
# User registration happens via the built-in endpoint
# POST /auth/register
{"name": "John Doe", "email": "john@example.com", "password": "secure_password"}
```

A password shorter than `AUTH_PASSWORD_MIN_LENGTH` is refused with a `422`, as it is on reset and change; with the default `0`, any length goes. An email is refused when an account already holds it in any case: `Jean@example.com` and `jean@example.com` are one address.

That refusal, a `400` with `Email already registered`, tells whoever asks that the address has an account: registration is the one built-in endpoint that does. The uniqueness whatever the case is checked by the code, not by the database: two registrations of two spellings of one address at the same instant can both go through.

Or create users programmatically:

```python
from fastedgy.depends.security import hash_password
from fastedgy.dependencies import Inject
from fastedgy.orm import Registry


async def create_user(name: str, email: str, password: str, registry: Registry = Inject(Registry)):
    User = registry.get_model("User")

    hashed_password = hash_password(password)
    user = User(name=name, email=email, password=hashed_password)
    await user.save()
    return user
```

## User login

```python
# Login via built-in endpoint
# POST /auth/token
{
    "username": "john@example.com",  # Email as username
    "password": "secure_password",
}

# Returns:
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer",
}
```

The email is matched whatever its case, so `JOHN@example.com` signs in the account of `john@example.com`. Two accounts left from before whose emails differ by case alone are told apart by the exact spelling: any other spelling signs in neither.

A login naming no account checks the password against a hash all the same, so it takes as long as one naming an account: the response time does not tell which addresses have one.

## Protecting endpoints

```python
from fastedgy.depends.security import get_current_user
from fastedgy.models.user import BaseUser
from fastapi import Depends


@app.get("/profile")
async def get_profile(current_user: BaseUser = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}


@app.post("/protected-action")
async def protected_action(data: dict, current_user: BaseUser = Depends(get_current_user)):
    # Only authenticated users can access this
    return {"message": f"Hello {current_user.name}", "data": data}
```

## Token refresh

```python
# Refresh access token via built-in endpoint
# POST /auth/refresh
{"refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."}

# Returns new access token
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer",
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

1. **Request reset**: `POST /auth/password/forgot`
2. **Validate token**: `POST /auth/password/validate`
3. **Reset password**: `POST /auth/password/reset`

```python
# 1. Request password reset
{"email": "john@example.com"}

# 2. User receives email with reset token
# 3. Reset password with token
{"token": "reset-token-from-email", "password": "new_secure_password"}
```

The request answers `200` with the same message whether an account holds the email or not, so it tells nobody which addresses have an account. The account is looked up, given its reset token and mailed once the response is out, so neither its existence nor a slow or failing database or mail server shows in the answer: a failure is logged. The email goes to an existing account only, matched whatever its case.

Each of these requests writes only its own columns, the reset token for this one, the password for a reset or a change: whatever another request changed meanwhile, a new password among it, stays as the row has it.

## Changing the password

```python
# POST /auth/password/change, with the access token
{"current_password": "secure_password", "new_password": "new_secure_password"}

# Returns a new pair of tokens beside the message
{
    "message": "Password changed successfully",
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer",
}
```

With `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true`, the tokens the request was made with stop working with the change: a client keeps its session by storing the pair the response returns. With the default, they keep working until they expire.

## Sessions end with a password change

This is off by default. With `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true`, each access and refresh token carries `pwf`, a short keyed fingerprint of the stored password hash. A token whose fingerprint no longer matches its account is refused by every route, by `/auth/refresh` and by the realtime socket, which is checked again at once. Changing or resetting a password therefore ends every session opened before, on every device. Tokens stay stateless: nothing is stored, and the check costs one HMAC on the account already read.

- A token without the claim, issued before the check existed, is accepted until it expires, and no password change can end it. Refreshing it returns tokens without the claim, whose refresh token expires when it does: a session opened before the check is never extended, and signs in again once, `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` at most after the check is turned on. Bound to the password of the moment instead, a stolen token would outlive a change of that password, rotation after rotation. Issuing the fingerprint first, as [Turning it on](#turning-it-on) describes, leaves no such session by then.
- Tokens your own code mints carry the claim when they are built from `token_claims(user)`. Built from `{"sub": email}`, they are never revoked this way, and once the check is on a refresh never extends them. `auth_token(user)` of the test kit builds them from `token_claims(user)`, so a test that changes a password sees its earlier tokens refused, as a client would.
- A new hash of the same password changes the fingerprint too. A login that upgrades a hash to the default hasher, bcrypt to argon2id for one, hands out tokens for the new hash, and tokens without the claim are not affected; any other session carrying the claim of the old hash ends, and its device signs in again once. Two first logins of one account at the same instant can end one another the same way.
- Personal API keys do not depend on the password and are not affected, a reset included.
- With both settings at their default `false`, tokens are minted without the claim, the claim of those already issued is not checked, a password change has no realtime socket checked again, and a refresh renews a session for a full lifetime, as before the check existed. Turning the revocation back off after it was on accepts every token again.

### Turning it on

An application nobody is signed in to yet sets `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true` once its clients, its own tokens and its instances are ready, as the first step below lists. Otherwise, no session open at that moment carries the claim, and each signs in again once within the next `AUTH_REFRESH_TOKEN_EXPIRE_DAYS`. `AUTH_PASSWORD_FINGERPRINT_TOKENS` spares them that by issuing the claim before it is checked, in two steps:

1. **Issue the fingerprint.** Set `AUTH_PASSWORD_FINGERPRINT_TOKENS=true`. A login, a refresh and a password change hand out tokens with the claim, and a refresh gives the claim of the current password to a session opened without it, for a full lifetime: sessions go on sliding as before. Nothing checks the claim yet, so a password change ends no session and has no realtime socket checked again. While this step runs:
    - publish the versions of your clients that store the pair `/auth/password/change` returns: once the check is on, the tokens a change was made with stop working, and a client that drops the new pair is signed out right after a change;
    - mint every token your own code issues from `token_claims(user)`, as below: a token built from `{"sub": email}` is never revoked, and once the check is on a refresh never extends it;
    - run this version on every instance: an older one mints tokens without the claim and ignores the one a token carries, so once the check is on it still accepts a revoked token.
2. **Check it.** At least `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` after the first step (30 days by default), and once your clients are published, set `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true` on every instance at once. Every session still open by then was opened or refreshed during the first step and carries the claim, so none signs in again for lack of it. The exception is a session that has not refreshed since a password change, a reset or a new hash of its account during the first step: its claim is the old one, and it signs in again. From then on, a password change or reset ends the sessions of its account. `AUTH_PASSWORD_FINGERPRINT_TOKENS` may stay on or go: with the check on, it changes nothing. Switch every instance together: while one still runs the first step, it renews a token another has just revoked, with the claim of the current password.

```python
from fastedgy.depends.security import create_access_token, create_refresh_token, token_claims
from fastedgy.models.user import BaseUser


def issue_tokens(user: BaseUser) -> dict[str, str]:
    claims = token_claims(user)

    return {"access_token": create_access_token(claims), "refresh_token": create_refresh_token(claims)}
```

The first step has a limit: nothing checks the claim a token carries, so a session that refreshes after a password change takes the fingerprint of the new password. Until the second step, a stolen token therefore outlives a password change, as it does without either setting; once the check is on, the next change ends it.

Once the check is on, expect a new hash of a password, a login upgrading bcrypt to argon2id among them, to end the other sessions of that account: their devices sign in again once. A new hash made during the first step does the same to a session that has not refreshed since, as soon as the check is on.

## Personal API keys

A JWT expires in minutes, which is no use to a script or an agent. An application built with
`FastEdgy(user_api_tokens=True)` also accepts a personal API key, on either header:

```bash
curl https://app.example.com/api/products -H "Authorization: Bearer acme_A1b2..."
curl https://app.example.com/api/products -H "X-Api-Token: acme_A1b2..."
```

A key authenticates every route with the rights of its owner, exactly where a JWT would. See the
[MCP Server guide](../mcp-server/guide.md) for creating, listing and revoking them.

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

- **400 Bad Request**: Email already registered, current password incorrect, reset token invalid or expired
- **401 Unauthorized**: Invalid credentials, or, with `AUTH_REVOKE_TOKENS_ON_PASSWORD_CHANGE=true`, a token issued before the password changed
- **422 Unprocessable Entity**: Invalid request data, a password shorter than a non-zero `AUTH_PASSWORD_MIN_LENGTH` among them, with the type `password_too_short` and the minimum in `ctx.min_length`

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
