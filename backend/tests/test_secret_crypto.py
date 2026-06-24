"""At-rest secret encryption tests (C9)."""

from __future__ import annotations

import pytest

from app.core.secret_crypto import decrypt_secret, encrypt_secret, is_encrypted


def test_encrypt_round_trip() -> None:
    token = encrypt_secret("sk-super-secret-value")
    assert is_encrypted(token)
    assert token.startswith("fernet:")
    assert "sk-super-secret-value" not in token  # plaintext not present in stored form
    assert decrypt_secret(token) == "sk-super-secret-value"


def test_legacy_plaintext_passthrough() -> None:
    # Rows written before encryption (no prefix) decrypt to themselves so reads keep working
    # until the backfill runs.
    assert not is_encrypted("legacy-plaintext-key")
    assert decrypt_secret("legacy-plaintext-key") == "legacy-plaintext-key"


def test_tampered_token_raises() -> None:
    token = encrypt_secret("value")
    tampered = token[:-4] + "AAAA"
    with pytest.raises(ValueError):
        decrypt_secret(tampered)
