import base64
import json

from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.routes.webhooks_checkr import _SIGNATURE_PLACEHOLDER, _compute_signature


@pytest.fixture(autouse=True)
def configure_checkr_secrets():
    original_api_key = settings.checkr_api_key
    original_user = settings.checkr_webhook_user
    original_pass = settings.checkr_webhook_pass
    settings.checkr_api_key = SecretStr("sk_test_signature")
    settings.checkr_webhook_user = SecretStr("hookuser")
    settings.checkr_webhook_pass = SecretStr("hookpass")
    try:
        yield
    finally:
        settings.checkr_api_key = original_api_key
        settings.checkr_webhook_user = original_user
        settings.checkr_webhook_pass = original_pass


def _signed_headers(body: bytes, signature: str | None = None) -> dict[str, str]:
    token = base64.b64encode(b"hookuser:hookpass").decode("utf-8")
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }
    secret_value = settings.checkr_api_key.get_secret_value()
    headers["X-Checkr-Signature"] = signature or _compute_signature(secret_value, body)
    return headers


def _raw_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def test_valid_signature_allows_processing(client):
    payload = {"type": "", "data": {"object": {"id": "noop"}}}
    raw_body = _raw_payload(payload)

    response = client.post(
        "/webhooks/checkr/",
        content=raw_body,
        headers=_signed_headers(raw_body),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_invalid_signature_logs_warning(client, caplog):
    payload = {"type": "", "data": {"object": {"id": "sig-mismatch"}}}
    raw_body = _raw_payload(payload)
    headers = _signed_headers(raw_body, signature="sha256=invalid")

    with caplog.at_level("WARNING"):
        response = client.post("/webhooks/checkr/", content=raw_body, headers=headers)

    assert response.status_code == 401
    assert "signature mismatch" in caplog.text


@pytest.mark.parametrize(
    "header_value",
    [
        None,
        _SIGNATURE_PLACEHOLDER,
    ],
)
def test_missing_or_placeholder_signature_rejected(client, header_value):
    payload = {"type": "", "data": {"object": {"id": "missing-header"}}}
    raw_body = _raw_payload(payload)
    headers = _signed_headers(raw_body)
    if header_value is None:
        headers.pop("X-Checkr-Signature")
    else:
        headers["X-Checkr-Signature"] = header_value

    response = client.post("/webhooks/checkr/", content=raw_body, headers=headers)

    assert response.status_code == 401
