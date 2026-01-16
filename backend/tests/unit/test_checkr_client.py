from __future__ import annotations

import httpx
from httpx import MockTransport, Response
from pydantic import SecretStr
import pytest

from app.integrations.checkr_client import CheckrClient, CheckrError, FakeCheckrClient


def test_create_candidate_includes_idempotency_header():
    captured: dict[str, str | None] = {}

    def handler(request):
        captured["Idempotency-Key"] = request.headers.get("Idempotency-Key")
        return Response(201, json={"id": "cand_123"})

    client = CheckrClient(
        api_key="sk_test",
        base_url="https://api.checkr.com/v1",
        transport=MockTransport(handler),
    )
    client.create_candidate(idempotency_key="candidate-123", first_name="Test")

    assert captured["Idempotency-Key"] == "candidate-123"


def test_create_candidate_omits_idempotency_header_without_key():
    captured: dict[str, str | None] = {}

    def handler(request):
        captured["Idempotency-Key"] = request.headers.get("Idempotency-Key")
        return Response(201, json={"id": "cand_456"})

    client = CheckrClient(
        api_key="sk_test",
        base_url="https://api.checkr.com/v1",
        transport=MockTransport(handler),
    )
    client.create_candidate(first_name="Test")

    assert captured["Idempotency-Key"] is None


def test_init_requires_api_key():
    with pytest.raises(ValueError, match="Checkr API key"):
        CheckrClient(api_key="")


def test_get_report_requires_id():
    client = CheckrClient(api_key="sk_test", transport=MockTransport(lambda request: Response(200)))
    with pytest.raises(ValueError, match="report_id"):
        client.get_report("")


def test_request_raises_checkr_error_with_json_body():
    def handler(request):
        return Response(
            401,
            json={"error": "invalid_api_key"},
            request=request,
        )

    client = CheckrClient(api_key="sk_test", transport=MockTransport(handler))
    with pytest.raises(CheckrError) as exc:
        client.request("GET", "/reports/rpt_123")
    assert exc.value.status_code == 401
    assert exc.value.error_type == "invalid_api_key"
    assert exc.value.error_body == {"error": "invalid_api_key"}


def test_request_raises_checkr_error_with_text_body():
    def handler(request):
        return Response(500, content=b"oops", request=request)

    client = CheckrClient(api_key="sk_test", transport=MockTransport(handler))
    with pytest.raises(CheckrError) as exc:
        client.request("GET", "/reports/rpt_123")
    assert exc.value.status_code == 500
    assert exc.value.error_body == "oops"


def test_request_raises_checkr_error_on_request_failure():
    def handler(request):
        raise httpx.RequestError("boom", request=request)

    client = CheckrClient(api_key="sk_test", transport=MockTransport(handler))
    with pytest.raises(CheckrError, match="Failed to reach Checkr API"):
        client.request("GET", "/reports/rpt_123")


def test_request_raises_on_invalid_json_response():
    def handler(request):
        return Response(200, content=b"{", request=request)

    client = CheckrClient(api_key="sk_test", transport=MockTransport(handler))
    with pytest.raises(CheckrError, match="malformed JSON"):
        client.request("GET", "/reports/rpt_123")


def test_request_logs_debug_and_returns_payload(caplog):
    def handler(request):
        return Response(200, json={"id": "rpt_123"}, request=request)

    client = CheckrClient(api_key="sk_test", transport=MockTransport(handler))
    caplog.set_level("DEBUG")
    payload = client.request("GET", "/reports/rpt_123")

    assert payload["id"] == "rpt_123"
    assert any("CheckrClient request" in record.getMessage() for record in caplog.records)


def test_create_invitation_filters_none_values():
    captured: dict[str, str | None] = {}

    def handler(request):
        captured["body"] = request.content.decode()
        return Response(201, json={"id": "inv_123"}, request=request)

    client = CheckrClient(api_key="sk_test", transport=MockTransport(handler))
    client.create_invitation(candidate_id="cand_123", package=None)

    assert '"package"' not in captured["body"]
    assert '"candidate_id"' in captured["body"]


def test_get_report_success():
    def handler(request):
        return Response(200, json={"id": "rpt_456"}, request=request)

    client = CheckrClient(api_key="sk_test", transport=MockTransport(handler))
    payload = client.get_report("rpt_456")
    assert payload["id"] == "rpt_456"


def test_accepts_secretstr_api_key():
    def handler(request):
        return Response(200, json={"id": "cand"}, request=request)

    client = CheckrClient(api_key=SecretStr("sk_test"), transport=MockTransport(handler))
    payload = client.create_candidate(first_name="Test")
    assert payload["id"] == "cand"


def test_fake_checkr_client_generates_ids():
    client = FakeCheckrClient()
    candidate = client.create_candidate(first_name="Test")
    assert candidate["id"].startswith("fake-candidate-")

    invitation = client.create_invitation(candidate_id=candidate["id"], package="basic")
    assert invitation["id"].startswith("inv_fake_")
    assert invitation["report_id"].startswith("rpt_fake_")

    report = client.get_report("")
    assert report["id"].startswith("rpt_fake_")
