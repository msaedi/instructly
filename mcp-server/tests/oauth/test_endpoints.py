"""Integration tests for OAuth endpoints."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from instainstru_mcp.config import Settings
from instainstru_mcp.oauth.endpoints import attach_oauth_routes
from instainstru_mcp.oauth.models import AuthorizationCode
from instainstru_mcp.oauth.storage import InMemoryStorage
from starlette.applications import Starlette
from starlette.testclient import TestClient


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


def _pkce_challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


class WorkOSStub:
    def __init__(self, domain: str, client_id: str, client_secret: str, id_token: str, jwks: dict):
        self.domain = domain
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = f"https://{domain}"
        self._id_token = id_token
        self._jwks = jwks

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        return f"{self.base_url}/oauth2/authorize?state={state}&redirect_uri={redirect_uri}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "workos-access", "id_token": self._id_token}

    async def get_userinfo(self, access_token: str) -> dict:
        return {"sub": "user123", "email": "admin@instainstru.com"}

    async def get_jwks(self) -> dict:
        return self._jwks


@pytest.fixture(scope="session")
def server_keys() -> dict[str, str]:
    private_pem, public_pem = _generate_keys()
    return {"private": private_pem, "public": public_pem}


@pytest.fixture(scope="session")
def workos_keys() -> dict[str, str]:
    private_pem, public_pem = _generate_keys()
    return {"private": private_pem, "public": public_pem}


def _build_workos_jwks(public_pem: str, kid: str) -> dict:
    public_key = serialization.load_pem_public_key(public_pem.encode())
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def _build_workos_id_token(private_pem: str, kid: str, issuer: str, audience: str) -> str:
    private_key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "sub": "user123",
        "aud": audience,
        "email": "admin@instainstru.com",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return pyjwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def _build_app(settings: Settings, storage: InMemoryStorage, workos_stub: WorkOSStub) -> TestClient:
    app = Starlette()
    with patch("instainstru_mcp.oauth.endpoints.WorkOSClient", return_value=workos_stub):
        attach_oauth_routes(app, settings, storage=storage)
    return TestClient(app, raise_server_exceptions=False)


def test_dcr_register_client(server_keys: dict[str, str], workos_keys: dict[str, str]):
    storage = InMemoryStorage()
    workos_jwks = _build_workos_jwks(workos_keys["public"], "workos-key")
    id_token = _build_workos_id_token(
        workos_keys["private"],
        "workos-key",
        issuer="https://workos.test",
        audience="workos-client",
    )
    workos_stub = WorkOSStub("workos.test", "workos-client", "secret", id_token, workos_jwks)

    settings = Settings(
        api_service_token="token",
        jwt_private_key=server_keys["private"],
        jwt_public_key=server_keys["public"],
        jwt_key_id="test-key",
        oauth_issuer="https://mcp.instainstru.com",
        workos_domain="workos.test",
        workos_client_id="workos-client",
        workos_client_secret="secret",
    )

    client = _build_app(settings, storage, workos_stub)
    response = client.post(
        "/oauth2/register",
        json={"client_name": "Test", "redirect_uris": ["https://example.com/callback"]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["client_id"].startswith("mcp_client_")
    assert payload["redirect_uris"] == ["https://example.com/callback"]


def test_authorize_callback_token_flow(server_keys: dict[str, str], workos_keys: dict[str, str]):
    storage = InMemoryStorage()
    workos_jwks = _build_workos_jwks(workos_keys["public"], "workos-key")
    id_token = _build_workos_id_token(
        workos_keys["private"],
        "workos-key",
        issuer="https://workos.test",
        audience="workos-client",
    )
    workos_stub = WorkOSStub("workos.test", "workos-client", "secret", id_token, workos_jwks)

    settings = Settings(
        api_service_token="token",
        jwt_private_key=server_keys["private"],
        jwt_public_key=server_keys["public"],
        jwt_key_id="test-key",
        oauth_issuer="https://mcp.instainstru.com",
        workos_domain="workos.test",
        workos_client_id="workos-client",
        workos_client_secret="secret",
    )

    client = _build_app(settings, storage, workos_stub)

    register = client.post(
        "/oauth2/register",
        json={"client_name": "Test", "redirect_uris": ["https://example.com/callback"]},
    )
    client_id = register.json()["client_id"]

    code_verifier = "verifier123"
    code_challenge = _pkce_challenge(code_verifier)
    response = client.get(
        "/oauth2/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "orig-state",
            "scope": "openid profile email",
            "resource": "https://mcp.instainstru.com",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    redirect_url = response.headers["location"]
    state = parse_qs(urlparse(redirect_url).query)["state"][0]

    callback = client.get(
        "/oauth2/callback",
        params={"code": "workos-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    callback_qs = parse_qs(urlparse(callback.headers["location"]).query)
    auth_code = callback_qs["code"][0]
    assert callback_qs["state"][0] == "orig-state"

    token_response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "https://example.com/callback",
            "code_verifier": code_verifier,
        },
    )
    assert token_response.status_code == 200
    token_payload = token_response.json()
    assert "access_token" in token_payload
    assert "refresh_token" in token_payload

    public_key = serialization.load_pem_public_key(server_keys["public"].encode())
    decoded = pyjwt.decode(
        token_payload["access_token"],
        public_key,
        algorithms=["RS256"],
        issuer="https://mcp.instainstru.com",
        audience="https://mcp.instainstru.com",
    )
    assert decoded["email"] == "admin@instainstru.com"

    refresh_response = client.post(
        "/oauth2/token",
        data={"grant_type": "refresh_token", "refresh_token": token_payload["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]


def test_invalid_redirect_uri_rejected(server_keys: dict[str, str], workos_keys: dict[str, str]):
    storage = InMemoryStorage()
    workos_jwks = _build_workos_jwks(workos_keys["public"], "workos-key")
    id_token = _build_workos_id_token(
        workos_keys["private"],
        "workos-key",
        issuer="https://workos.test",
        audience="workos-client",
    )
    workos_stub = WorkOSStub("workos.test", "workos-client", "secret", id_token, workos_jwks)

    settings = Settings(
        api_service_token="token",
        jwt_private_key=server_keys["private"],
        jwt_public_key=server_keys["public"],
        jwt_key_id="test-key",
        oauth_issuer="https://mcp.instainstru.com",
        workos_domain="workos.test",
        workos_client_id="workos-client",
        workos_client_secret="secret",
    )

    client = _build_app(settings, storage, workos_stub)
    response = client.post(
        "/oauth2/register",
        json={"client_name": "Test", "redirect_uris": ["http://example.com/callback"]},
    )
    assert response.status_code == 400


def test_expired_auth_code_rejected(server_keys: dict[str, str], workos_keys: dict[str, str]):
    storage = InMemoryStorage()
    workos_jwks = _build_workos_jwks(workos_keys["public"], "workos-key")
    id_token = _build_workos_id_token(
        workos_keys["private"],
        "workos-key",
        issuer="https://workos.test",
        audience="workos-client",
    )
    workos_stub = WorkOSStub("workos.test", "workos-client", "secret", id_token, workos_jwks)

    settings = Settings(
        api_service_token="token",
        jwt_private_key=server_keys["private"],
        jwt_public_key=server_keys["public"],
        jwt_key_id="test-key",
        oauth_issuer="https://mcp.instainstru.com",
        workos_domain="workos.test",
        workos_client_id="workos-client",
        workos_client_secret="secret",
    )

    client = _build_app(settings, storage, workos_stub)

    expired_code = AuthorizationCode(
        code="expired",
        user_id="user123",
        user_email="admin@instainstru.com",
        client_id="client123",
        redirect_uri="https://example.com/callback",
        code_challenge="challenge",
        resource=None,
        scope="openid",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=6),
    )
    storage.save_auth_code(expired_code)

    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": "expired",
            "redirect_uri": "https://example.com/callback",
            "code_verifier": "verifier",
        },
    )
    assert response.status_code == 400


def test_invalid_code_verifier_rejected(server_keys: dict[str, str], workos_keys: dict[str, str]):
    storage = InMemoryStorage()
    workos_jwks = _build_workos_jwks(workos_keys["public"], "workos-key")
    id_token = _build_workos_id_token(
        workos_keys["private"],
        "workos-key",
        issuer="https://workos.test",
        audience="workos-client",
    )
    workos_stub = WorkOSStub("workos.test", "workos-client", "secret", id_token, workos_jwks)

    settings = Settings(
        api_service_token="token",
        jwt_private_key=server_keys["private"],
        jwt_public_key=server_keys["public"],
        jwt_key_id="test-key",
        oauth_issuer="https://mcp.instainstru.com",
        workos_domain="workos.test",
        workos_client_id="workos-client",
        workos_client_secret="secret",
    )

    client = _build_app(settings, storage, workos_stub)

    register = client.post(
        "/oauth2/register",
        json={"client_name": "Test", "redirect_uris": ["https://example.com/callback"]},
    )
    client_id = register.json()["client_id"]

    code_verifier = "verifier123"
    code_challenge = _pkce_challenge(code_verifier)
    response = client.get(
        "/oauth2/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": "orig-state",
            "scope": "openid profile email",
        },
        follow_redirects=False,
    )
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]

    callback = client.get(
        "/oauth2/callback",
        params={"code": "workos-code", "state": state},
        follow_redirects=False,
    )
    auth_code = parse_qs(urlparse(callback.headers["location"]).query)["code"][0]

    token_response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "https://example.com/callback",
            "code_verifier": "wrong-verifier",
        },
    )
    assert token_response.status_code == 400


def test_metadata_and_jwks(server_keys: dict[str, str], workos_keys: dict[str, str]):
    storage = InMemoryStorage()
    workos_jwks = _build_workos_jwks(workos_keys["public"], "workos-key")
    id_token = _build_workos_id_token(
        workos_keys["private"],
        "workos-key",
        issuer="https://workos.test",
        audience="workos-client",
    )
    workos_stub = WorkOSStub("workos.test", "workos-client", "secret", id_token, workos_jwks)

    settings = Settings(
        api_service_token="token",
        jwt_private_key=server_keys["private"],
        jwt_public_key=server_keys["public"],
        jwt_key_id="test-key",
        oauth_issuer="https://mcp.instainstru.com",
        workos_domain="workos.test",
        workos_client_id="workos-client",
        workos_client_secret="secret",
    )

    client = _build_app(settings, storage, workos_stub)

    metadata = client.get("/.well-known/oauth-authorization-server")
    assert metadata.status_code == 200
    meta_payload = metadata.json()
    assert meta_payload["issuer"] == "https://mcp.instainstru.com"
    assert meta_payload["authorization_endpoint"].endswith("/oauth2/authorize")

    resource = client.get("/.well-known/oauth-protected-resource")
    assert resource.status_code == 200
    resource_payload = resource.json()
    assert resource_payload["resource"] == "https://mcp.instainstru.com/sse"
    assert resource_payload["authorization_servers"] == ["https://mcp.instainstru.com"]

    jwks = client.get("/.well-known/jwks.json")
    assert jwks.status_code == 200
    jwks_payload = jwks.json()
    assert jwks_payload["keys"][0]["kid"] == "test-key"
