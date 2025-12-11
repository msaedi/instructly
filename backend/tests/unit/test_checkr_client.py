from __future__ import annotations

from httpx import MockTransport, Response

from app.integrations.checkr_client import CheckrClient


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
