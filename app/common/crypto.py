"""AES-GCM encryption helpers."""
from __future__ import annotations

import os
from base64 import urlsafe_b64decode, urlsafe_b64encode

try:  # pragma: no cover - cryptography might not be available
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover
    AESGCM = None  # type: ignore

from .errors import CryptoError


def generate_key() -> str:
    """Return a new random 256-bit key encoded for storage."""
    if not AESGCM:
        raise CryptoError("cryptography library is required for AES-GCM")
    return urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()


def encrypt(plaintext: bytes, key: str) -> str:
    """Encrypt ``plaintext`` with ``key`` returning a base64 token."""
    if not AESGCM:
        raise CryptoError("cryptography library is required for AES-GCM")
    aesgcm = AESGCM(urlsafe_b64decode(key))
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(token: str, key: str) -> bytes:
    """Decrypt a base64 ``token`` created by :func:`encrypt`."""
    if not AESGCM:
        raise CryptoError("cryptography library is required for AES-GCM")
    data = urlsafe_b64decode(token)
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(urlsafe_b64decode(key))
    return aesgcm.decrypt(nonce, ciphertext, None)


__all__ = ["generate_key", "encrypt", "decrypt"]
