# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from cryptography.fernet import Fernet, InvalidToken

from fastedgy.config import BaseSettings
from fastedgy.dependencies import Inject
from fastedgy.i18n import _t


class VaultError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class VaultLocked(VaultError):
    """No key in the settings: nothing can be sealed or opened."""


class VaultUnreadable(VaultError):
    """A secret sealed with another key, or damaged: it has to be asked for again."""


class Vault:
    """Seals the secrets the application keeps (provider tokens, account keys) with the Fernet key of the
    deployment, `SECRETS_ENCRYPTION_KEY`. A sealed secret never leaves a payload: the vault is the only one to read it.
    """

    def __init__(self, settings: BaseSettings = Inject(BaseSettings)):
        self._settings = settings

    @property
    def is_ready(self) -> bool:
        return bool(self._settings.secrets_encryption_key)

    def _cipher(self) -> Fernet:
        key = self._settings.secrets_encryption_key

        if not key:
            raise VaultLocked(str(_t("No encryption key is configured (SECRETS_ENCRYPTION_KEY)")))

        return Fernet(key.encode())

    def seal(self, value: str) -> str:
        return self._cipher().encrypt(value.encode()).decode()

    def open(self, sealed: str) -> str:
        try:
            return self._cipher().decrypt(sealed.encode()).decode()
        except (InvalidToken, ValueError) as cause:
            raise VaultUnreadable(str(_t("The secret cannot be read with the current encryption key"))) from cause


def generate_key() -> str:
    return Fernet.generate_key().decode()


__all__ = ["Vault", "VaultError", "VaultLocked", "VaultUnreadable", "generate_key"]
