import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag

from app.modules.integrations.crypto import (
    decrypt_credentials,
    encrypt_credentials,
    register_key,
)


@pytest.fixture(autouse=True)
def setup_test_key():
    test_key = os.urandom(32)
    register_key(1, test_key)
    # Also register key version 2 for rotation tests
    test_key_v2 = os.urandom(32)
    register_key(2, test_key_v2)


def test_roundtrip_encryption_decryption():
    tenant_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    payload = {
        "access_token": "EAAB1234567890",
        "phone_number_id": "100200300",
        "waba_id": "999888777",
    }

    encrypted = encrypt_credentials(payload, tenant_id, integration_id, key_version=1)
    assert isinstance(encrypted, bytes)
    assert len(encrypted) > 29

    decrypted = decrypt_credentials(encrypted, tenant_id, integration_id)
    assert decrypted == payload


def test_aad_mismatch_fails_decryption():
    tenant_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    different_integration_id = uuid.uuid4()
    different_tenant_id = uuid.uuid4()

    payload = {"access_token": "secret_token"}
    encrypted = encrypt_credentials(payload, tenant_id, integration_id)

    # Copied to different integration_id in same tenant
    with pytest.raises(InvalidTag):
        decrypt_credentials(encrypted, tenant_id, different_integration_id)

    # Copied to different tenant
    with pytest.raises(InvalidTag):
        decrypt_credentials(encrypted, different_tenant_id, integration_id)


def test_tampered_ciphertext_fails_decryption():
    tenant_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    payload = {"token": "secret"}

    encrypted = bytearray(encrypt_credentials(payload, tenant_id, integration_id))
    # Tamper with the last byte of tag
    encrypted[-1] ^= 0x01

    with pytest.raises(InvalidTag):
        decrypt_credentials(bytes(encrypted), tenant_id, integration_id)


def test_key_versioning_and_rotation():
    tenant_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    payload = {"token": "v2_secret"}

    # Encrypt with version 2
    encrypted_v2 = encrypt_credentials(payload, tenant_id, integration_id, key_version=2)
    assert encrypted_v2[0] == 2

    # Decrypt reads version byte and uses key v2
    decrypted = decrypt_credentials(encrypted_v2, tenant_id, integration_id)
    assert decrypted == payload

    # Unknown key version raises KeyError
    unknown_version_blob = bytes([99]) + encrypted_v2[1:]
    with pytest.raises(KeyError):
        decrypt_credentials(unknown_version_blob, tenant_id, integration_id)


def test_invalid_length_ciphertext_raises_value_error():
    tenant_id = uuid.uuid4()
    integration_id = uuid.uuid4()

    with pytest.raises(ValueError, match="too short"):
        decrypt_credentials(b"short", tenant_id, integration_id)
