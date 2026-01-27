"""Cryptographic utilities for OAuth."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization


def normalize_pem(pem: str) -> str:
    """Normalize PEM strings loaded from env vars."""
    cleaned = pem.strip()
    if "\\r\\n" in cleaned:
        cleaned = cleaned.replace("\\r\\n", "\n")
    if "\\n" in cleaned:
        cleaned = cleaned.replace("\\n", "\n")
    return cleaned


def load_rsa_keys(private_pem: str, public_pem: str) -> tuple[Any, Any]:
    """Load RSA keys from PEM strings."""
    private_key = serialization.load_pem_private_key(
        normalize_pem(private_pem).encode(),
        password=None,
    )
    public_key = serialization.load_pem_public_key(normalize_pem(public_pem).encode())
    return private_key, public_key


def sign_jwt(
    payload: dict,
    private_key,
    key_id: str,
    algorithm: str = "RS256",
) -> str:
    """Sign a JWT with our private key."""
    return jwt.encode(payload, private_key, algorithm=algorithm, headers={"kid": key_id})


def verify_pkce(code_verifier: str, code_challenge: str, method: str = "S256") -> bool:
    """Verify PKCE code_verifier matches code_challenge."""
    if method != "S256":
        raise ValueError("Only S256 supported")
    computed = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return secrets.compare_digest(computed, code_challenge)


def generate_code(length: int = 32) -> str:
    """Generate cryptographically secure random code."""
    return secrets.token_urlsafe(length)


def build_jwks(public_key, key_id: str) -> dict:
    """Build JWKS JSON from public key."""
    jwk_json = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk_json.update({"kid": key_id, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk_json]}
