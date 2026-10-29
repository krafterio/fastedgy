# Vault

The vault seals the secrets your application keeps on behalf of its users (a provider token, the keys of an account they connect) with one Fernet key of the deployment. A sealed secret is written to the database as an opaque string, and the vault is the only piece of code that opens it again.

```python
from fastedgy.dependencies import get_service
from fastedgy.vault import Vault

vault = get_service(Vault)
connection.sealed_token = vault.seal(token)
```

## Why use it

- **One key per deployment**: `SECRETS_ENCRYPTION_KEY`, generated once, kept out of the database and of the code.
- **Nothing to remember**: Fernet signs and encrypts, so a secret altered in the database fails to open instead of opening wrong.
- **Clear failures**: a missing key and a secret sealed with another key raise two distinct errors, so an application can ask for the secret again rather than crash.

## Key features

- `Vault.seal(value)` and `Vault.open(sealed)`, both on strings
- `Vault.is_ready`: whether a key is configured
- `VaultLocked` when no key is configured, `VaultUnreadable` when a secret cannot be opened with the current key
- `generate_key()` gives a new key for the settings

## Next steps

- [Usage Guide](guide.md): configure the key, seal and open a secret, handle a lost key
