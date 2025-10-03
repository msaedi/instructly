"""Lightweight helpers for encrypting sensitive strings."""

from __future__ import annotations

from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

_FERNET_INSTANCE: Optional[Fernet] = None
_FERNET_KEY: Optional[str] = None


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
