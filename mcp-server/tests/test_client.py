from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, call, patch

import httpx
import pytest
import respx
from instainstru_mcp.auth import AuthenticationError, MCPAuth
from instainstru_mcp.client import (
    BackendAuthError,
    BackendConnectionError,
    BackendNotFoundError,
    BackendRequestError,
    InstaInstruClient,
    TokenCache,
    _secret_value,
)
from instainstru_mcp.config import Settings
from pydantic import SecretStr


@pytest.mark.asyncio
@respx.mock
async def test_client_success():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, json={"data": {"ok": True}}
    )

    result = await client.get_funnel_summary()
    assert result["data"]["ok"] is True
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_call_passes_custom_headers():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, json={"data": {"ok": True}}
    )

    await client.call(
        "GET",
        "/api/v1/admin/mcp/founding/funnel",
        headers={"X-Custom": "yes"},
    )
    assert route.calls[0].request.headers.get("X-Custom") == "yes"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_auth_error():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(401)

    with pytest.raises(BackendAuthError):
        await client.get_funnel_summary()
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_not_found():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(404)

    with pytest.raises(BackendNotFoundError):
        await client.get_funnel_summary()
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_network_error():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").mock(
        side_effect=httpx.ConnectError("boom")
    )

    with pytest.raises(BackendConnectionError):
        await client.get_funnel_summary()
    await client.aclose()


def test_secret_value_handles_secretstr_and_none():
    assert _secret_value(None) == ""
    assert _secret_value("token") == "token"
    assert _secret_value(SecretStr("secret")) == "secret"


def test_token_cache_expires_entries():
    cache = TokenCache()
    cache.set("token", expires_in=120)
    assert cache.get() == "token"
    cache._expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert cache.get() is None


@pytest.mark.asyncio
@respx.mock
async def test_client_uses_m2m_token_and_caches():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="secret",
        workos_m2m_token_url="https://workos.test/oauth/token",
        workos_m2m_audience="https://api.instainstru.test",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    token_route = respx.post("https://workos.test/oauth/token").respond(
        200, json={"access_token": "m2m-token", "expires_in": 3600}
    )
    api_route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, json={"data": {"ok": True}}
    )

    await client.get_funnel_summary()
    await client.get_funnel_summary()

    assert token_route.call_count == 1
    assert api_route.call_count == 2
    assert api_route.calls[0].request.headers.get("Authorization") == "Bearer m2m-token"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_falls_back_to_static_token_on_m2m_failure():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="secret",
        workos_m2m_token_url="https://workos.test/oauth/token",
        workos_m2m_audience="https://api.instainstru.test",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.post("https://workos.test/oauth/token").respond(500)
    api_route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, json={"data": {"ok": True}}
    )

    result = await client.get_funnel_summary()
    assert result["data"]["ok"] is True
    assert api_route.calls[0].request.headers.get("Authorization") == "Bearer svc"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_m2m_failure_without_static_token_raises():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="secret",
        workos_m2m_token_url="https://workos.test/oauth/token",
        workos_m2m_audience="https://api.instainstru.test",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.post("https://workos.test/oauth/token").respond(500)

    with pytest.raises(BackendConnectionError):
        await client.get_funnel_summary()

    await client.aclose()


@pytest.mark.asyncio
async def test_client_timeout_uses_explicit_timeout_value():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with patch.object(
        client.http, "request", new=AsyncMock(side_effect=httpx.TimeoutException("boom"))
    ):
        with pytest.raises(BackendConnectionError, match="timed out after 5.0s"):
            await client.call("GET", "/api/v1/admin/mcp/founding/funnel", timeout=5.0)

    await client.aclose()


@pytest.mark.asyncio
async def test_client_timeout_uses_httpx_timeout_read_value():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with patch.object(
        client.http, "request", new=AsyncMock(side_effect=httpx.TimeoutException("boom"))
    ):
        timeout = httpx.Timeout(4.0)
        with pytest.raises(BackendConnectionError, match="4.0s"):
            await client.call("GET", "/api/v1/admin/mcp/founding/funnel", timeout=timeout)

    await client.aclose()


@pytest.mark.asyncio
async def test_client_timeout_uses_client_default_timeout():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)
    client.http.timeout = httpx.Timeout(7.0)

    with patch.object(
        client.http, "request", new=AsyncMock(side_effect=httpx.TimeoutException("boom"))
    ):
        with pytest.raises(BackendConnectionError, match="7.0s"):
            await client.call("GET", "/api/v1/admin/mcp/founding/funnel")

    await client.aclose()


@pytest.mark.asyncio
async def test_client_timeout_without_read_timeout_message(monkeypatch):
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)
    client.http.timeout = httpx.Timeout(None)

    with patch.object(
        client.http, "request", new=AsyncMock(side_effect=httpx.TimeoutException("boom"))
    ):
        with pytest.raises(BackendConnectionError, match="timed out"):
            await client.call("GET", "/api/v1/admin/mcp/founding/funnel")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_returns_text_when_response_is_not_json():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, text="not-json"
    )

    result = await client.get_funnel_summary()
    assert result["status_code"] == 200
    assert result["text"] == "not-json"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_raises_request_error_on_500():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(500)

    with pytest.raises(BackendRequestError, match="backend_error_500"):
        await client.get_funnel_summary()

    await client.aclose()


@pytest.mark.asyncio
async def test_client_missing_tokens_raises_auth_error(monkeypatch):
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_ID", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_TOKEN_URL", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_AUDIENCE", raising=False)
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="",
        workos_m2m_client_id="",
        workos_m2m_client_secret="",
        workos_m2m_token_url="",
        workos_m2m_audience="",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with pytest.raises(AuthenticationError):
        await client._get_bearer_token()

    await client.aclose()


@pytest.mark.asyncio
async def test_client_static_token_used_when_no_m2m(monkeypatch):
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_ID", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_TOKEN_URL", raising=False)
    monkeypatch.delenv("INSTAINSTRU_MCP_WORKOS_M2M_AUDIENCE", raising=False)
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
        workos_m2m_client_id="",
        workos_m2m_client_secret="",
        workos_m2m_token_url="",
        workos_m2m_audience="",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    token = await client._get_bearer_token()
    assert token == "svc"

    await client.aclose()


@pytest.mark.asyncio
async def test_client_m2m_missing_credentials_raises():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="",
        workos_m2m_token_url="https://workos.test/oauth/token",
        workos_m2m_audience="https://api.instainstru.test",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with pytest.raises(BackendConnectionError, match="m2m_client_credentials_missing"):
        await client._get_access_token()

    await client.aclose()


@pytest.mark.asyncio
async def test_client_wrapper_methods_call_expected_paths():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mock_call = AsyncMock(return_value={"ok": True})
    with patch.object(client, "call", mock_call):
        await client.get_funnel_summary(start_date="2026-01-01", end_date="2026-01-31")
        await client.get_stuck_instructors(stuck_days=10, stage="profile", limit=5)
        await client.list_instructors(status="live", service_slug="guitar", limit=10)
        await client.get_instructor_coverage(status="live", group_by="service", top=3)
        await client.preview_invites(recipient_emails=["a@example.com"])
        await client.send_invites(confirm_token="token", idempotency_key="idem")
        await client.list_invites(email="a@example.com", status="pending", limit=25)
        await client.get_invite_detail("INV1")
        await client.get_services_catalog()
        await client.lookup_service("swim")
        await client.get_top_queries(start_date="2026-01-01", end_date="2026-01-31", limit=5)
        await client.get_zero_results(start_date="2026-01-01", end_date="2026-01-31", limit=5)
        await client.get_metric("instructor.live")
        await client.get_celery_workers()
        await client.get_celery_queues()
        await client.get_celery_failed_tasks(limit=5)
        await client.get_celery_payment_health()
        await client.get_celery_active_tasks()
        await client.get_celery_task_history(task_name="task", state="SUCCESS", hours=2, limit=10)
        await client.get_celery_beat_schedule()
        await client.get_booking_summary(period="last_7_days")
        await client.get_booking_summary(start_date="2026-01-01", end_date="2026-01-07")
        await client.get_recent_bookings(status="confirmed", limit=10, hours=48)
        await client.get_payment_pipeline()
        await client.get_pending_payouts(limit=5)
        await client.refund_preview(
            booking_id="01BOOK",
            reason_code="GOODWILL",
            amount_type="full",
            amount_value=None,
            note="note",
        )
        await client.refund_execute(confirm_token="token", idempotency_key="idem")
        await client.lookup_user(identifier="user@example.com")
        await client.get_user_booking_history(user_id="01USER", limit=15)

    expected = [
        call(
            "GET",
            "/api/v1/admin/mcp/founding/funnel",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/founding/stuck",
            params={"stuck_days": 10, "limit": 5, "stage": "profile"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/instructors",
            params={"status": "live", "service_slug": "guitar", "limit": 10},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/instructors/coverage",
            params={"status": "live", "group_by": "service", "top": 3},
        ),
        call(
            "POST",
            "/api/v1/admin/mcp/invites/preview",
            json={"recipient_emails": ["a@example.com"]},
            timeout=60.0,
        ),
        call(
            "POST",
            "/api/v1/admin/mcp/invites/send",
            json={"confirm_token": "token", "idempotency_key": "idem"},
            headers={"Idempotency-Key": "idem"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/invites",
            params={"email": "a@example.com", "status": "pending", "limit": 25},
        ),
        call("GET", "/api/v1/admin/mcp/invites/INV1"),
        call("GET", "/api/v1/admin/mcp/services/catalog"),
        call(
            "GET",
            "/api/v1/admin/mcp/services/lookup",
            params={"q": "swim"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/search/top-queries",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31", "limit": 5},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/search/zero-results",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31", "limit": 5},
        ),
        call("GET", "/api/v1/admin/mcp/metrics/instructor.live"),
        call("GET", "/api/v1/admin/mcp/celery/workers"),
        call("GET", "/api/v1/admin/mcp/celery/queues"),
        call(
            "GET",
            "/api/v1/admin/mcp/celery/failed",
            params={"limit": 5},
        ),
        call("GET", "/api/v1/admin/mcp/celery/payment-health"),
        call("GET", "/api/v1/admin/mcp/celery/tasks/active"),
        call(
            "GET",
            "/api/v1/admin/mcp/celery/tasks/history",
            params={"hours": 2, "limit": 10, "task_name": "task", "state": "SUCCESS"},
        ),
        call("GET", "/api/v1/admin/mcp/celery/schedule"),
        call(
            "GET",
            "/api/v1/admin/mcp/ops/bookings/summary",
            params={"period": "last_7_days"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/ops/bookings/summary",
            params={"start_date": "2026-01-01", "end_date": "2026-01-07"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/ops/bookings/recent",
            params={"limit": 10, "hours": 48, "status": "confirmed"},
        ),
        call("GET", "/api/v1/admin/mcp/ops/payments/pipeline"),
        call(
            "GET",
            "/api/v1/admin/mcp/ops/payments/pending-payouts",
            params={"limit": 5},
        ),
        call(
            "POST",
            "/api/v1/admin/mcp/refunds/preview",
            json={
                "booking_id": "01BOOK",
                "reason_code": "GOODWILL",
                "amount": {"type": "full", "value": None},
                "note": "note",
            },
        ),
        call(
            "POST",
            "/api/v1/admin/mcp/refunds/execute",
            json={"confirm_token": "token", "idempotency_key": "idem"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/ops/users/lookup",
            params={"identifier": "user@example.com"},
        ),
        call(
            "GET",
            "/api/v1/admin/mcp/ops/users/01USER/bookings",
            params={"limit": 15},
        ),
    ]
    assert mock_call.call_args_list == expected

    await client.aclose()


@pytest.mark.asyncio
async def test_instructor_detail_url_encodes_name_with_spaces():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with patch.object(client, "call") as mock_call:
        mock_call.return_value = {"data": {}}
        await client.get_instructor_detail("Jane Doe")
        mock_call.assert_called_once_with(
            "GET",
            "/api/v1/admin/mcp/instructors/Jane%20Doe",
        )

    await client.aclose()


@pytest.mark.asyncio
async def test_client_get_booking_detail_calls_expected_path():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mock_call = AsyncMock(return_value={"ok": True})
    with patch.object(client, "call", mock_call):
        await client.get_booking_detail(
            "01BOOK 123",
            include_messages_summary=True,
            include_webhooks=False,
            include_trace_links=True,
        )

    mock_call.assert_called_once_with(
        "GET",
        "/api/v1/admin/mcp/bookings/01BOOK%20123/detail",
        params={
            "include_messages_summary": True,
            "include_webhooks": False,
            "include_trace_links": True,
        },
    )

    await client.aclose()


@pytest.mark.asyncio
async def test_client_refund_preview_requires_amount_value_for_partial():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with pytest.raises(ValueError, match="amount_value is required"):
        await client.refund_preview(
            booking_id="01BOOK",
            reason_code="GOODWILL",
            amount_type="partial",
            amount_value=None,
        )

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_webhook_endpoints():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    list_route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/webhooks").respond(
        200, json={"ok": True}
    )
    failed_route = respx.get(
        "https://api.instainstru.test/api/v1/admin/mcp/webhooks/failed"
    ).respond(200, json={"ok": True})
    respx.get("https://api.instainstru.test/api/v1/admin/mcp/webhooks/evt_123").respond(
        200, json={"ok": True}
    )
    replay_route = respx.post(
        "https://api.instainstru.test/api/v1/admin/mcp/webhooks/evt_123/replay"
    ).respond(200, json={"ok": True})

    await client.get_webhooks(
        source="stripe",
        status="failed",
        event_type="payment_intent.failed",
        since_hours=12,
        limit=10,
    )
    await client.get_webhooks(
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-02T00:00:00Z",
        limit=5,
    )
    await client.get_failed_webhooks(source="checkr", since_hours=48, limit=5)
    await client.get_failed_webhooks(
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-02T00:00:00Z",
        limit=3,
    )
    await client.get_webhook_detail("evt_123")
    await client.replay_webhook("evt_123", dry_run=False)

    assert list_route.calls[0].request.url.params["source"] == "stripe"
    assert list_route.calls[0].request.url.params["status"] == "failed"
    assert list_route.calls[0].request.url.params["event_type"] == "payment_intent.failed"
    assert list_route.calls[1].request.url.params["start_time"] == "2026-01-01T00:00:00Z"
    assert list_route.calls[1].request.url.params["end_time"] == "2026-01-02T00:00:00Z"
    assert failed_route.calls[0].request.url.params["source"] == "checkr"
    assert failed_route.calls[1].request.url.params["start_time"] == "2026-01-01T00:00:00Z"
    assert failed_route.calls[1].request.url.params["end_time"] == "2026-01-02T00:00:00Z"
    assert replay_route.calls[0].request.url.params["dry_run"] == "false"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_audit_endpoints():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    search_route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/audit/search").respond(
        200, json={"ok": True}
    )
    user_route = respx.get(
        "https://api.instainstru.test/api/v1/admin/mcp/audit/users/user%40example.com/activity"
    ).respond(200, json={"ok": True})
    resource_route = respx.get(
        "https://api.instainstru.test/api/v1/admin/mcp/audit/resources/booking/01HXY1234567890ABCDEFGHJKL/history"
    ).respond(200, json={"ok": True})
    recent_route = respx.get(
        "https://api.instainstru.test/api/v1/admin/mcp/audit/admin-actions/recent"
    ).respond(200, json={"ok": True})

    await client.audit_search(actor_email="user@example.com", action="booking.cancel", limit=5)
    await client.audit_search(
        actor_email="user2@example.com",
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-02T00:00:00Z",
        limit=3,
    )
    await client.audit_user_activity("user@example.com", since_days=7, limit=5)
    await client.audit_user_activity(
        "user@example.com",
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-02T00:00:00Z",
        limit=4,
    )
    await client.audit_resource_history(
        "booking",
        "01HXY1234567890ABCDEFGHJKL",
        limit=3,
    )
    await client.audit_resource_history(
        "booking",
        "01HXY1234567890ABCDEFGHJKL",
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-02T00:00:00Z",
        limit=2,
    )
    await client.audit_recent_admin_actions(since_hours=6, limit=10)
    await client.audit_recent_admin_actions(
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-02T00:00:00Z",
        limit=7,
    )

    assert search_route.calls[0].request.url.params["actor_email"] == "user@example.com"
    assert search_route.calls[0].request.url.params["action"] == "booking.cancel"
    assert search_route.calls[0].request.url.params["limit"] == "5"
    assert search_route.calls[1].request.url.params["start_time"] == "2026-01-01T00:00:00Z"
    assert search_route.calls[1].request.url.params["end_time"] == "2026-01-02T00:00:00Z"
    assert user_route.calls[0].request.url.params["since_days"] == "7"
    assert user_route.calls[0].request.url.params["limit"] == "5"
    assert user_route.calls[1].request.url.params["start_time"] == "2026-01-01T00:00:00Z"
    assert user_route.calls[1].request.url.params["end_time"] == "2026-01-02T00:00:00Z"
    assert resource_route.calls[0].request.url.params["limit"] == "3"
    assert resource_route.calls[1].request.url.params["start_time"] == "2026-01-01T00:00:00Z"
    assert resource_route.calls[1].request.url.params["end_time"] == "2026-01-02T00:00:00Z"
    assert recent_route.calls[0].request.url.params["since_hours"] == "6"
    assert recent_route.calls[0].request.url.params["limit"] == "10"
    assert recent_route.calls[1].request.url.params["start_time"] == "2026-01-01T00:00:00Z"
    assert recent_route.calls[1].request.url.params["end_time"] == "2026-01-02T00:00:00Z"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_celery_failed_tasks_clamps_limit():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    failed_route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/celery/failed").respond(
        200, json={"ok": True}
    )

    await client.get_celery_failed_tasks(limit=200)
    await client.get_celery_failed_tasks(limit=20.0)
    await client.get_celery_failed_tasks(limit="bad")

    assert failed_route.calls[0].request.url.params["limit"] == "100"
    assert failed_route.calls[1].request.url.params["limit"] == "20"
    assert failed_route.calls[2].request.url.params["limit"] == "50"

    await client.aclose()


@pytest.mark.asyncio
async def test_client_booking_summary_requires_dates():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with pytest.raises(ValueError):
        await client.get_booking_summary(start_date="2026-01-01")

    with pytest.raises(ValueError):
        await client.get_booking_summary(end_date="2026-01-07")

    await client.aclose()


@pytest.mark.asyncio
async def test_client_time_window_requires_both_dates():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with pytest.raises(ValueError):
        await client.get_webhooks(start_time="2026-01-01T00:00:00Z")

    with pytest.raises(ValueError):
        await client.get_failed_webhooks(end_time="2026-01-02T00:00:00Z")

    with pytest.raises(ValueError):
        await client.audit_search(start_time="2026-01-01T00:00:00Z")

    with pytest.raises(ValueError):
        await client.audit_user_activity("user@example.com", start_time="2026-01-01T00:00:00Z")

    with pytest.raises(ValueError):
        await client.audit_resource_history("booking", "01HXY", end_time="2026-01-02T00:00:00Z")

    with pytest.raises(ValueError):
        await client.audit_recent_admin_actions(start_time="2026-01-01T00:00:00Z")

    with pytest.raises(ValueError):
        await client.get_payment_timeline(booking_id="01BOOK", start_time="2026-01-01T00:00:00Z")

    await client.aclose()


@pytest.mark.asyncio
async def test_client_payment_timeline_requires_identifier():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with pytest.raises(ValueError):
        await client.get_payment_timeline()

    with pytest.raises(ValueError):
        await client.get_payment_timeline(booking_id="01BOOK", user_id="01USER")

    await client.aclose()


@pytest.mark.asyncio
async def test_client_payment_timeline_with_user_and_time_window():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mock_call = AsyncMock(return_value={"ok": True})
    client.call = mock_call

    await client.get_payment_timeline(
        user_id="01USER",
        start_time="2026-02-01T00:00:00Z",
        end_time="2026-02-02T00:00:00Z",
    )

    assert mock_call.await_count == 1
    params = mock_call.await_args.kwargs["params"]
    assert params == {
        "user_id": "01USER",
        "start_time": "2026-02-01T00:00:00Z",
        "end_time": "2026-02-02T00:00:00Z",
    }

    await client.aclose()


@pytest.mark.asyncio
async def test_client_payment_timeline_since_hours_normalization():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mock_call = AsyncMock(return_value={"ok": True})
    client.call = mock_call

    await client.get_payment_timeline(booking_id="01BOOK", since_hours="bad")  # type: ignore[arg-type]

    params = mock_call.await_args.kwargs["params"]
    assert params["booking_id"] == "01BOOK"
    assert params["since_hours"] == 24

    await client.aclose()


@pytest.mark.asyncio
async def test_client_payment_timeline_since_days_normalization():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mock_call = AsyncMock(return_value={"ok": True})
    client.call = mock_call

    await client.get_payment_timeline(booking_id="01BOOK", since_days="bad")  # type: ignore[arg-type]

    params = mock_call.await_args.kwargs["params"]
    assert params["booking_id"] == "01BOOK"
    assert params["since_days"] == 30

    await client.aclose()


@pytest.mark.asyncio
async def test_client_audit_user_activity_since_hours():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mock_call = AsyncMock(return_value={"ok": True})
    client.call = mock_call

    await client.audit_user_activity("user@example.com", since_hours=12)

    params = mock_call.await_args.kwargs["params"]
    assert params["since_hours"] == 12

    await client.aclose()


@pytest.mark.asyncio
async def test_client_audit_resource_history_since_hours():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    mock_call = AsyncMock(return_value={"ok": True})
    client.call = mock_call

    await client.audit_resource_history("booking", "01HXY", since_hours=6)

    params = mock_call.await_args.kwargs["params"]
    assert params["since_hours"] == 6

    await client.aclose()
