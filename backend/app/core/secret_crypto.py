"""At-rest encryption for stored project secrets (Fernet).

The ``secrets`` table previously stored provider keys/tokens in plaintext. This module
encrypts them with Fernet (AES-128-CBC + HMAC). Values are tagged with a ``fernet:``
prefix so encrypted and legacy-plaintext rows can coexist during/after the one-time
backfill (``app/commands/encrypt_secrets.py``): :func:`decrypt_secret` returns a
non-prefixed value unchanged, so reads keep working before the backfill runs.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# Marker distinguishing encrypted values from legacy plaintext rows.
_ENC_PREFIX = "fernet:"


def _derive_fernet_key(source: str) -> bytes:
    """Derive a valid urlsafe-base64 Fernet key from an arbitrary string."""
    digest = hashlib.sha256(source.encode()).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    configured = (getattr(settings, "SECRET_ENCRYPTION_KEY", "") or "").strip()
    if configured:
        try:
            # Accept a ready-made Fernet key directly.
            return Fernet(configured.encode())
        except (ValueError, TypeError):
            # Otherwise derive one deterministically from the provided string.
            return Fernet(_derive_fernet_key(configured))
    # No dedicated key set — derive from SECRET_KEY so deployments work out of the box.
    return Fernet(_derive_fernet_key(settings.SECRET_KEY))


def is_encrypted(stored: str) -> bool:
    """True if ``stored`` is a Fernet-encrypted value produced by this module."""
    return stored.startswith(_ENC_PREFIX)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret for storage (returns a ``fernet:``-prefixed token)."""
    token = _fernet().encrypt(plaintext.encode()).decode()
    return f"{_ENC_PREFIX}{token}"


def decrypt_secret(stored: str) -> str:
    """Decrypt a stored secret. Legacy (non-prefixed) plaintext is returned unchanged."""
    if not is_encrypted(stored):
        return stored
    token = stored[len(_ENC_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt secret — SECRET_ENCRYPTION_KEY/SECRET_KEY mismatch or corrupt data."
        ) from exc
