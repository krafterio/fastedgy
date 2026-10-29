# Vault usage guide

## Configure the key

Generate the key once per deployment and put it in the environment of the application:

```python
from fastedgy.vault import generate_key

print(generate_key())
```

```bash
SECRETS_ENCRYPTION_KEY=...
```

The setting is `secrets_encryption_key` on `BaseSettings`. Losing the key makes every sealed secret unreadable; changing it has the same effect on the secrets sealed with the previous one.

## Seal a secret before saving it

```python
from fastedgy.dependencies import get_service
from fastedgy.vault import Vault


async def connect(connection, token: str) -> None:
    connection.sealed_token = get_service(Vault).seal(token)
    await connection.save()
```

Never return the sealed value, or the secret itself, in a payload: keep the column out of the schemas and let only the code that calls the provider open it.

## Open it where it is used

```python
from fastedgy.vault import Vault, VaultUnreadable


def token_of(connection, vault: Vault) -> str | None:
    try:
        return vault.open(connection.sealed_token)
    except VaultUnreadable:
        return None
```

`VaultUnreadable` means the secret was sealed with another key, or damaged: the usual answer is to mark the connection as broken and ask the user to connect again.

## Without a key

`Vault.is_ready` is false when no key is configured, and `seal` or `open` then raise `VaultLocked`. Check it before offering a feature that needs a secret, so that a development environment without a key shows the feature as unavailable instead of failing on save.

```python
if not get_service(Vault).is_ready:
    raise HTTPException(status_code=503, detail="The vault is not configured")
```
