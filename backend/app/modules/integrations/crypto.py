"""AES-256-GCM credentials encryption with AAD binding.

Credentials are write-only and encrypted before storage in integrations.credentials_encrypted.
The Extra Authenticated Data (AAD) binds tenant_id:integration_id, ensuring ciphertext
copied to another tenant or row cannot be decrypted.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

__all__ = [
    "decrypt_credentials",
    "encrypt_credentials",
    "get_key",
    "register_key",
    "InvalidTag",
]

_keyring: dict[int, bytes] = {}

NONCE_LENGTH = 12
TAG_LENGTH = 16
MIN_CIPHERTEXT_LENGTH = 1 + NONCE_LENGTH + TAG_LENGTH


def register_key(version: int, key: bytes | str) -> None:
    """Register an encryption key for a given key_version (e.g. for key rotation/testing)."""
    if isinstance(key, str):
        raw = base64.b64decode(key.strip())
    else:
        raw = key
    if len(raw) != 32:
        raise ValueError("Encryption key must be exactly 32 bytes (256 bits)")
    _keyring[version] = raw


def get_key(version: int = 1) -> bytes:
    """Retrieve the key for the specified version from keyring or app settings."""
    if version in _keyring:
        return _keyring[version]

    if version == 1:
        raw_secret = settings.integration_encryption_key.get_secret_value().strip()
        if not raw_secret:
            raise RuntimeError(
                "INTEGRATION_ENCRYPTION_KEY is not configured in settings."
            )
        try:
            decoded = base64.b64decode(raw_secret)
        except Exception as exc:
            raise ValueError("INTEGRATION_ENCRYPTION_KEY must be base64-encoded") from exc

        if len(decoded) != 32:
            raise ValueError("INTEGRATION_ENCRYPTION_KEY must decode to 32 bytes")

        _keyring[version] = decoded
        return decoded

    raise KeyError(f"No encryption key found for key_version {version}")


def encrypt_credentials(
    plaintext: dict[str, Any],
    tenant_id: str | uuid.UUID,
    integration_id: str | uuid.UUID,
    key_version: int = 1,
) -> bytes:
    """Encrypt credentials dictionary with AES-256-GCM.

    Wire format:
      [1 byte: key_version] [12 bytes: nonce] [ciphertext + 16 bytes: tag]
    """
    key = get_key(key_version)
    nonce = os.urandom(NONCE_LENGTH)
    aad = f"{tenant_id}:{integration_id}".encode("utf-8")
    payload_bytes = json.dumps(plaintext, separators=(",", ":"), sort_keys=True).encode("utf-8")

    ct_and_tag = AESGCM(key).encrypt(nonce, payload_bytes, aad)
    return bytes([key_version]) + nonce + ct_and_tag


def decrypt_credentials(
    ciphertext: bytes,
    tenant_id: str | uuid.UUID,
    integration_id: str | uuid.UUID,
) -> dict[str, Any]:
    """Decrypt credentials blob with AES-256-GCM and verify AAD.

    Raises:
      InvalidTag: If ciphertext is tampered with, wrong key, or AAD mismatch.
      ValueError: If ciphertext wire format is invalid.
      KeyError: If the key_version in the blob is not recognized.
    """
    if len(ciphertext) < MIN_CIPHERTEXT_LENGTH:
        raise ValueError("Ciphertext too short to contain valid version, nonce, and tag")

    version = ciphertext[0]
    nonce = ciphertext[1 : 1 + NONCE_LENGTH]
    ct_and_tag = ciphertext[1 + NONCE_LENGTH :]

    key = get_key(version)
    aad = f"{tenant_id}:{integration_id}".encode("utf-8")

    # AESGCM.decrypt raises InvalidTag if verification fails
    plain_bytes = AESGCM(key).decrypt(nonce, ct_and_tag, aad)
    return json.loads(plain_bytes.decode("utf-8"))
