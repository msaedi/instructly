from importlib import reload

from cryptography.fernet import Fernet
import pytest

from app.core import config as cfg, crypto


def _set_key(monkeypatch: pytest.MonkeyPatch, key: str | None) -> None:
    if key is None:
        monkeypatch.setenv("BGC_ENCRYPTION_KEY", "")
    else:
        monkeypatch.setenv("BGC_ENCRYPTION_KEY", key)
    reload(cfg)
    reload(crypto)


def test_encrypt_decrypt_roundtrip_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    _set_key(monkeypatch, key)
    plaintext = "abc123!"

    token = crypto.encrypt_str(plaintext)

    assert token != plaintext
    assert crypto.decrypt_str(token) == plaintext


def test_decrypt_with_wrong_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    _set_key(monkeypatch, key)
    token = crypto.encrypt_str("secret")

    other = Fernet.generate_key().decode()
    _set_key(monkeypatch, other)

    with pytest.raises(ValueError):
        crypto.decrypt_str(token)


def test_no_key_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, None)
    plaintext = "keep-plain"

    assert crypto.encrypt_str(plaintext) == plaintext
    assert crypto.decrypt_str(plaintext) == plaintext
