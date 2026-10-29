# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import pytest

from fastedgy.config import BaseSettings
from fastedgy.vault import Vault, VaultLocked, VaultUnreadable, generate_key


def vault_with(key: str) -> Vault:
    return Vault(BaseSettings(database_url="postgresql+asyncpg://localhost/vault", secrets_encryption_key=key))


def test_a_sealed_secret_opens_with_the_same_key() -> None:
    vault = vault_with(generate_key())

    sealed = vault.seal("token")

    assert sealed != "token"
    assert vault.open(sealed) == "token"


def test_without_a_key_nothing_is_sealed() -> None:
    vault = vault_with("")

    assert not vault.is_ready
    with pytest.raises(VaultLocked):
        vault.seal("token")


def test_a_secret_sealed_with_another_key_is_unreadable() -> None:
    sealed = vault_with(generate_key()).seal("token")

    with pytest.raises(VaultUnreadable):
        vault_with(generate_key()).open(sealed)
