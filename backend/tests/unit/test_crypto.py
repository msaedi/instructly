import base64
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


def test_validate_key_length_and_encryption_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_key = base64.urlsafe_b64encode(b"short").decode()
    with pytest.raises(RuntimeError):
        crypto.validate_bgc_encryption_key(bad_key)

    _set_key(monkeypatch, None)
    with pytest.raises(RuntimeError):
        crypto.assert_encryption_ready()


def test_report_token_pass_through_and_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, None)
    assert crypto.encrypt_report_token("") == ""
    assert crypto.encrypt_report_token("plain") == "plain"
    assert crypto.decrypt_report_token("") == ""
    assert crypto.decrypt_report_token("plain") == "plain"

    bad_key = base64.urlsafe_b64encode(b"short").decode()
    _set_key(monkeypatch, bad_key)
    with pytest.raises(ValueError):
        crypto.encrypt_report_token("report-1")


def test_report_token_invalid_tag_and_encryption_available(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    _set_key(monkeypatch, key)
    token = crypto.encrypt_report_token("report-2")

    other = Fernet.generate_key().decode()
    _set_key(monkeypatch, other)
    with pytest.raises(ValueError):
        crypto.decrypt_report_token(token)

    _set_key(monkeypatch, "not-base64")
    assert crypto.encryption_available() is False
