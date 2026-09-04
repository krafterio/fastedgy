# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import re
from typing import Protocol, runtime_checkable

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ARGON2_PREFIX = re.compile(r"^\$argon2(id|i|d)\$")
BCRYPT_PREFIX = re.compile(r"^\$2[abxy]\$")


@runtime_checkable
class Hasher(Protocol):
    """One password hashing scheme: what it recognises, and how it hashes."""

    id: str

    def supports(self, hashed: str) -> bool: ...

    def hash(self, raw: str) -> str: ...

    def verify(self, raw: str, hashed: str) -> bool: ...


class Argon2idHasher:
    """RFC 9106 second recommended profile, also the OWASP minimum: 19 MiB of
    memory, 2 passes, no lane parallelism.

    Roughly a fifth of bcrypt's cost at factor 12 while being memory-hard,
    which is what makes it resistant to GPU and ASIC cracking. Memory is the
    parameter to watch: it is held for the duration of each hash, so the
    concurrency of the callers is what sets the real footprint.
    """

    id = "argon2id"

    def __init__(self, memory_cost: int = 19456, time_cost: int = 2, parallelism: int = 1) -> None:
        self._hasher = PasswordHasher(memory_cost=memory_cost, time_cost=time_cost, parallelism=parallelism)

    def supports(self, hashed: str) -> bool:
        return bool(ARGON2_PREFIX.match(hashed))

    def hash(self, raw: str) -> str:
        return self._hasher.hash(raw)

    def verify(self, raw: str, hashed: str) -> bool:
        try:
            return self._hasher.verify(hashed, raw)
        except VerifyMismatchError, VerificationError, InvalidHashError:
            return False


class BcryptHasher:
    """Kept to verify the hashes already in the database.

    Never selected as the default: it is only here so accounts created before
    the switch keep working, and get rehashed on their next successful login.
    """

    id = "bcrypt"

    @staticmethod
    def _to_bytes(raw: str) -> bytes:
        # bcrypt only considers the first 72 bytes; truncating keeps hashes
        # produced by the previous passlib-based implementation verifiable.
        return raw.encode("utf-8")[:72]

    def supports(self, hashed: str) -> bool:
        return bool(BCRYPT_PREFIX.match(hashed))

    def hash(self, raw: str) -> str:
        return bcrypt.hashpw(self._to_bytes(raw), bcrypt.gensalt()).decode("utf-8")

    def verify(self, raw: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(self._to_bytes(raw), hashed.encode("utf-8"))
        except ValueError:
            return False


class HasherRegistry:
    """The hashing schemes an application accepts, and which one it writes.

    Verification picks the scheme by the hash's own prefix, so a base holding
    several generations keeps working. ``needs_rehash`` tells a successful
    login that the stored hash is from an older scheme and can be upgraded in
    place, which is how a base migrates without asking anyone to reset a
    password.
    """

    def __init__(self, default_id: str = "argon2id") -> None:
        self._hashers: list[Hasher] = [Argon2idHasher(), BcryptHasher()]
        self._default_id = default_id

    def register(self, hasher: Hasher) -> None:
        self._hashers = [hasher, *(h for h in self._hashers if h.id != hasher.id)]

    def set_default(self, hasher_id: str) -> None:
        if not any(h.id == hasher_id for h in self._hashers):
            raise ValueError(f"No hasher registered with id {hasher_id!r}")

        self._default_id = hasher_id

    @property
    def default(self) -> Hasher:
        for hasher in self._hashers:
            if hasher.id == self._default_id:
                return hasher

        raise ValueError(f"No hasher registered with id {self._default_id!r}")

    def find(self, hashed: str | None) -> Hasher | None:
        if not hashed:
            return None

        return next((h for h in self._hashers if h.supports(hashed)), None)

    def hash(self, raw: str) -> str:
        return self.default.hash(raw)

    def verify(self, raw: str | None, hashed: str | None) -> bool:
        if not raw or not hashed:
            return False

        hasher = self.find(hashed)

        return hasher.verify(raw, hashed) if hasher else False

    def is_hashed(self, value: str | None) -> bool:
        return self.find(value) is not None

    def needs_rehash(self, hashed: str | None) -> bool:
        return bool(hashed) and not self.default.supports(hashed or "")


_fallback_registry: "HasherRegistry | None" = None


def get_hasher_registry() -> HasherRegistry:
    """The application's registry, or a default one outside a running app
    (scripts, one-off tooling), so hashing never depends on the container.
    """
    global _fallback_registry

    from fastedgy.dependencies import get_service, has_service

    if has_service(HasherRegistry):
        return get_service(HasherRegistry)

    if _fallback_registry is None:
        _fallback_registry = HasherRegistry()

    return _fallback_registry


__all__ = [
    "ARGON2_PREFIX",
    "BCRYPT_PREFIX",
    "Argon2idHasher",
    "BcryptHasher",
    "Hasher",
    "HasherRegistry",
    "get_hasher_registry",
]
