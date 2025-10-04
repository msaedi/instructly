"""Lightweight helpers for encrypting sensitive strings."""

from __future__ import annotations

import base64
from typing import Optional, cast

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .config import settings

_FERNET_INSTANCE: Optional[Fernet] = None
_FERNET_KEY: Optional[str] = None
_AES_KEY: Optional[bytes] = None


def validate_bgc_encryption_key(key: str | None) -> None:
    """Raise RuntimeError when the configured encryption key is unusable."""

    if not key:
        raise RuntimeError("BGC_ENCRYPTION_KEY must be configured when running in production.")

    try:
        decoded = base64.urlsafe_b64decode(key.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - configuration error surfaced at startup
        raise RuntimeError("BGC_ENCRYPTION_KEY is invalid (not urlsafe base64).") from exc

    if len(decoded) != 32:
        raise RuntimeError("BGC_ENCRYPTION_KEY must decode to 32 bytes.")


def _decoded_key() -> Optional[bytes]:
    """Decode the configured encryption key for AES operations."""

    global _AES_KEY, _FERNET_KEY

    key = getattr(settings, "bgc_encryption_key", None)
    if not key:
        _FERNET_KEY = None
        _AES_KEY = None
        return None

    if _AES_KEY is not None and _FERNET_KEY == key:
        return _AES_KEY

    try:
        key_bytes = base64.urlsafe_b64decode(key.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - misconfiguration
        raise ValueError("Invalid BGC_ENCRYPTION_KEY; expected urlsafe base64 string") from exc

    if len(key_bytes) != 32:
        raise ValueError("Invalid BGC_ENCRYPTION_KEY; expected decoded length of 32 bytes")

    _FERNET_KEY = key
    _AES_KEY = key_bytes
    return key_bytes


def _aes_cipher() -> Optional[Cipher]:
    """Return an AES cipher for compact report-id encryption."""

    key_bytes = _decoded_key()
    if key_bytes is None:
        return None
    return Cipher(algorithms.AES(key_bytes), modes.ECB())


def _fernet() -> Optional[Fernet]:
    """Return a memoized Fernet instance when encryption key configured."""

    global _FERNET_INSTANCE, _FERNET_KEY

    key = getattr(settings, "bgc_encryption_key", None)
    if not key:
        return None

    if _FERNET_INSTANCE is not None and _FERNET_KEY == key:
        return _FERNET_INSTANCE

    try:
        _FERNET_INSTANCE = Fernet(key.encode("utf-8"))
        _FERNET_KEY = key
        return _FERNET_INSTANCE
    except Exception as exc:  # pragma: no cover - configuration error
        raise ValueError("Invalid BGC_ENCRYPTION_KEY; expected base64-encoded 32-byte key") from exc


def encrypt_str(plain: str) -> str:
    """Encrypt a string with Fernet when configured; return original otherwise."""

    cipher = _fernet()
    if cipher is None or plain == "":
        return plain
    token: bytes = cipher.encrypt(plain.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_str(token: str) -> str:
    """Decrypt a Fernet token when configured; return original otherwise."""

    cipher = _fernet()
    if cipher is None or token == "":
        return token

    try:
        decrypted: bytes = cipher.decrypt(token.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken as exc:  # pragma: no cover - indicates tampering or wrong key
        raise ValueError("Unable to decrypt background check token") from exc


def encrypt_report_token(plain: str) -> str:
    """Encrypt a background-check report id using compact AES blocks."""

    if plain == "":
        return plain

    cipher = _aes_cipher()
    if cipher is None:
        return plain

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain.encode("utf-8")) + padder.finalize()

    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    token = base64.urlsafe_b64encode(encrypted).decode("utf-8").rstrip("=")
    return f"v1:{token}"


def decrypt_report_token(token: str) -> str:
    """Decrypt compact AES report identifiers (fallback to plaintext)."""

    if token == "":
        return token

    cipher = _aes_cipher()
    if cipher is None:
        return token

    if not token.startswith("v1:"):
        return token

    payload = token[3:]
    padding_len = (-len(payload)) % 4
    padded_payload = payload + ("=" * padding_len)

    try:
        encrypted = base64.urlsafe_b64decode(padded_payload.encode("utf-8"))
    except Exception as exc:
        raise ValueError("Unable to decode background check token") from exc

    decryptor = cipher.decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    data = unpadder.update(padded) + unpadder.finalize()
    return cast(str, data.decode("utf-8"))


def assert_encryption_ready() -> None:
    """Ensure background-check encryption is fully configured."""

    try:
        cipher = _fernet()
    except ValueError as exc:  # pragma: no cover - configuration error surfaced at startup
        raise RuntimeError(
            "BGC_ENCRYPTION_KEY is invalid; expected base64-encoded 32-byte key."
        ) from exc

    if cipher is None:
        raise RuntimeError("BGC_ENCRYPTION_KEY must be configured when running in production.")


def encryption_available() -> bool:
    """Return True when background-check encryption is configured."""

    try:
        return _fernet() is not None
    except ValueError:
        return False


__all__ = [
    "encrypt_str",
    "decrypt_str",
    "encrypt_report_token",
    "decrypt_report_token",
    "assert_encryption_ready",
    "encryption_available",
    "validate_bgc_encryption_key",
]
