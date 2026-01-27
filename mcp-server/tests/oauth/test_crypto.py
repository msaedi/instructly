"""Tests for OAuth crypto utilities."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from instainstru_mcp.oauth.crypto import build_jwks, generate_code, sign_jwt, verify_pkce


def _generate_keys() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


def test_verify_pkce_success():
    verifier = "test-verifier"
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert verify_pkce(verifier, challenge) is True


def test_verify_pkce_invalid():
    assert verify_pkce("verifier", "different") is False


def test_verify_pkce_requires_s256():
    with pytest.raises(ValueError):
        verify_pkce("verifier", "challenge", method="plain")


def test_sign_jwt_and_build_jwks():
    private_pem, public_pem = _generate_keys()
    private_key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    public_key = serialization.load_pem_public_key(public_pem.encode())

    now = datetime.now(timezone.utc)
    payload = {
        "iss": "https://issuer.example",
        "sub": "user123",
        "aud": "https://issuer.example",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }

    token = sign_jwt(payload, private_key, "test-key")
    decoded = pyjwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        issuer="https://issuer.example",
        audience="https://issuer.example",
    )
    assert decoded["sub"] == "user123"

    jwks = build_jwks(public_key, "test-key")
    assert jwks["keys"][0]["kid"] == "test-key"


def test_generate_code_returns_value():
    code = generate_code()
    assert isinstance(code, str)
    assert len(code) > 0
