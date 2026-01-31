from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from instainstru_mcp.clients.sentry_client import (
    SentryAuthError,
    SentryClient,
    SentryConnectionError,
    SentryNotConfiguredError,
    SentryNotFoundError,
    SentryRateLimitError,
    SentryRequestError,
    _decode_response,
    _extract_error_message,
    _parse_retry_after,
    _secret_value,
)
from instainstru_mcp.tools import sentry as sentry_tools
from pydantic import SecretStr


class FakeSentryClient:
    def __init__(
        self,
        *,
        issues: list[dict] | None = None,
        issue: dict | None = None,
        event: dict | None = None,
        resolved: dict | None = None,
        project_event: dict | None = None,
    ) -> None:
        self.issues = issues or []
        self.issue = issue or {}
        self.event = event or {}
        self.resolved = resolved or {}
        self.project_event = project_event or {}
        self.calls: list[tuple[str, dict]] = []
        self.org = "instainstru"

    async def list_issues(self, **kwargs):
        self.calls.append(("list_issues", kwargs))
        return self.issues

    async def get_issue(self, issue_id: int):
        self.calls.append(("get_issue", {"issue_id": issue_id}))
        return self.issue

    async def get_issue_event(
        self, issue_id: int, event_type: str, *, environment: str | None = None
    ):
        self.calls.append(
            (
                "get_issue_event",
                {"issue_id": issue_id, "event_type": event_type, "environment": environment},
            )
        )
        return self.event

    async def resolve_event_id(self, event_id: str):
        self.calls.append(("resolve_event_id", {"event_id": event_id}))
        return self.resolved

    async def get_project_event(self, project_slug: str, event_id: str):
        self.calls.append(
            ("get_project_event", {"project_slug": project_slug, "event_id": event_id})
        )
        return self.project_event


def _mock_scope(monkeypatch):
    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(sentry_tools, "get_http_request", fake_request)


def _mock_scope_with(monkeypatch, auth: dict):
    def fake_request():
        class Dummy:
            scope = {"auth": auth}

        return Dummy()

    monkeypatch.setattr(sentry_tools, "get_http_request", fake_request)


def _sample_issue():
    return {
        "id": "123",
        "shortId": "INST-1",
        "title": "RuntimeError: Connection timeout",
        "project": {"slug": "instainstru-api"},
        "culprit": "app.services.booking_service",
        "count": "5",
        "userCount": "2",
        "firstSeen": "2026-01-28T10:00:00Z",
        "lastSeen": "2026-01-30T21:30:00Z",
        "level": "error",
        "status": "unresolved",
        "permalink": "https://sentry.io/organizations/instainstru/issues/123/",
    }


def _sample_event():
    return {
        "eventID": "abc123def456",
        "title": "RuntimeError: Connection timeout",
        "message": "Connection timeout after 30s",
        "timestamp": "2026-01-30T21:30:00Z",
        "environment": "production",
        "release": "v1.2.3",
        "tags": [["browser", "Chrome 120"], ["os", "macOS"]],
        "user": {"id": "user_abc123", "email": "john@example.com"},
        "request": {
            "method": "POST",
            "url": "/api/v1/bookings",
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "session=abc",
                "X-API-Key": "key",
                "X-Request-ID": "req-123",
            },
        },
        "entries": [
            {
                "type": "exception",
                "data": {
                    "values": [
                        {
                            "stacktrace": {
                                "frames": [
                                    {
                                        "filename": "file1.py",
                                        "lineno": 10,
                                        "function": "func1",
                                        "context_line": "line1",
                                    },
                                    {
                                        "filename": "file2.py",
                                        "lineno": 20,
                                        "function": "func2",
                                        "context_line": "line2",
                                    },
                                    {
                                        "filename": "file3.py",
                                        "lineno": 30,
                                        "function": "func3",
                                        "context_line": "line3",
                                    },
                                ]
                            }
                        }
                    ]
                },
            }
        ],
    }


@pytest.mark.asyncio
@respx.mock
async def test_issues_top_default_params(monkeypatch):
    _mock_scope(monkeypatch)
    client = SentryClient("token", org="instainstru")

    issues_route = respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(
        200, json=[_sample_issue()]
    )

    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, client)

    result = await tools["instainstru_sentry_issues_top"]()

    params = issues_route.calls[0].request.url.params
    assert params.get("project") == "-1"
    assert params.get("environment") == "production"
    assert params.get("statsPeriod") == "24h"
    assert params.get("sort") == "user"
    assert params.get("query") == "is:unresolved"
    assert params.get("per_page") == "10"
    assert result["summary"]["total_events"] == 5
    assert result["summary"]["users_affected"] == 2

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_issues_top_project_filter(monkeypatch):
    _mock_scope(monkeypatch)
    client = SentryClient("token", org="instainstru")

    projects_route = respx.get(
        "https://sentry.io/api/0/organizations/instainstru/projects/"
    ).respond(200, json=[{"slug": "instainstru-api", "id": "42"}])

    issues_route = respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(
        200, json=[_sample_issue()]
    )

    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, client)

    await tools["instainstru_sentry_issues_top"](project="api")

    assert projects_route.called is True
    params = issues_route.calls[0].request.url.params
    assert params.get("project") == "42"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_issues_top_status_mapping(monkeypatch):
    _mock_scope(monkeypatch)
    client = SentryClient("token", org="instainstru")

    issues_route = respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(
        200, json=[_sample_issue()]
    )

    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, client)

    await tools["instainstru_sentry_issues_top"](status="resolved")

    params = issues_route.calls[0].request.url.params
    assert params.get("query") == "is:resolved"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_issues_top_caching(monkeypatch):
    _mock_scope(monkeypatch)
    client = SentryClient("token", org="instainstru")

    issues_route = respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(
        200, json=[_sample_issue()]
    )

    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, client)

    await tools["instainstru_sentry_issues_top"]()
    await tools["instainstru_sentry_issues_top"]()

    assert issues_route.call_count == 1

    await client.aclose()


@pytest.mark.asyncio
async def test_issue_detail_validates_numeric_id(monkeypatch):
    _mock_scope(monkeypatch)
    fake = FakeSentryClient()
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_issue_detail"]("INST-1")
    assert result["error"] == "invalid_request"


@pytest.mark.asyncio
async def test_issue_detail_redacts_email(monkeypatch):
    _mock_scope(monkeypatch)
    event = _sample_event()
    fake = FakeSentryClient(issue=_sample_issue(), event=event)
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_issue_detail"](123)
    assert result["event"]["user"]["email"] == "j***@example.com"


@pytest.mark.asyncio
async def test_issue_detail_strips_auth_headers(monkeypatch):
    _mock_scope(monkeypatch)
    event = _sample_event()
    fake = FakeSentryClient(issue=_sample_issue(), event=event)
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_issue_detail"](123)
    headers = result["event"]["request"]["headers"]
    assert "Authorization" not in headers
    assert "Cookie" not in headers
    assert "X-API-Key" not in headers
    assert headers["X-Request-ID"] == "req-123"


@pytest.mark.asyncio
async def test_issue_detail_truncates_stacktrace(monkeypatch):
    _mock_scope(monkeypatch)
    event = _sample_event()
    fake = FakeSentryClient(issue=_sample_issue(), event=event)
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_issue_detail"](123, max_frames=2)
    stacktrace = result["event"]["stacktrace"]
    assert stacktrace.count('File "') == 2
    assert "file1.py" not in stacktrace


@pytest.mark.asyncio
async def test_event_lookup_found(monkeypatch):
    _mock_scope(monkeypatch)
    event = _sample_event()
    fake = FakeSentryClient(
        issue=_sample_issue(),
        resolved={"projectSlug": "instainstru-api", "groupId": 123},
        project_event=event,
    )
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_event_lookup"]("abc123def456")
    assert result["found"] is True
    assert result["project"] == "instainstru-api"
    assert result["event"]["id"] == "abc123def456"
    assert result["issue"]["short_id"] == "INST-1"


@pytest.mark.asyncio
async def test_event_lookup_not_found(monkeypatch):
    _mock_scope(monkeypatch)

    class NotFoundClient(FakeSentryClient):
        async def resolve_event_id(self, event_id: str):
            raise SentryNotFoundError("sentry_not_found")

    fake = NotFoundClient()
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_event_lookup"]("missing")
    assert result["found"] is False
    assert result["event_id"] == "missing"
    assert len(result["suggestions"]) >= 1


@pytest.mark.asyncio
async def test_event_lookup_redacts_data(monkeypatch):
    _mock_scope(monkeypatch)
    event = _sample_event()
    fake = FakeSentryClient(
        issue=_sample_issue(),
        resolved={"projectSlug": "instainstru-api", "groupId": 123},
        project_event=event,
    )
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_event_lookup"]("abc123def456")
    assert result["event"]["user"]["email"] == "j***@example.com"
    headers = result["event"]["request"]["headers"]
    assert "Authorization" not in headers
    assert "Cookie" not in headers


@pytest.mark.asyncio
async def test_issues_top_all_sort_options(monkeypatch):
    _mock_scope(monkeypatch)
    fake = FakeSentryClient(issues=[_sample_issue()])
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    for sort_by in ["freq", "user", "new", "date", "trends"]:
        result = await tools["instainstru_sentry_issues_top"](sort_by=sort_by)
        assert result["summary"]["issues_returned"] == 1

    called_sorts = [call[1]["sort"] for call in fake.calls if call[0] == "list_issues"]
    assert called_sorts == ["freq", "user", "new", "date", "trends"]


@pytest.mark.asyncio
async def test_issues_top_query_override(monkeypatch):
    _mock_scope(monkeypatch)
    fake = FakeSentryClient(issues=[_sample_issue()])
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    raw_query = 'error.type:RuntimeError user.email:"test@example.com"'
    await tools["instainstru_sentry_issues_top"](status="all", query=raw_query)

    assert fake.calls[0][1]["query"] == raw_query


@pytest.mark.asyncio
async def test_issues_top_environment_filter(monkeypatch):
    _mock_scope(monkeypatch)
    fake = FakeSentryClient(issues=[_sample_issue()])
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    await tools["instainstru_sentry_issues_top"](environment="preview")
    assert fake.calls[0][1]["environment"] == "preview"


@pytest.mark.asyncio
async def test_issue_detail_no_stacktrace(monkeypatch):
    _mock_scope(monkeypatch)
    event = _sample_event()
    fake = FakeSentryClient(issue=_sample_issue(), event=event)
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_issue_detail"](123, include_stacktrace=False)
    assert "stacktrace" not in result["event"]


@pytest.mark.asyncio
@respx.mock
async def test_issue_detail_all_event_types(monkeypatch):
    _mock_scope(monkeypatch)
    client = SentryClient("token", org="instainstru")

    issue_route = respx.get(
        "https://sentry.io/api/0/organizations/instainstru/issues/123/"
    ).respond(200, json=_sample_issue())

    event_routes = {}
    for event_type in ["latest", "oldest", "recommended"]:
        event_routes[event_type] = respx.get(
            f"https://sentry.io/api/0/organizations/instainstru/issues/123/events/{event_type}/"
        ).respond(200, json=_sample_event())

    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, client)

    for event_type, route in event_routes.items():
        await tools["instainstru_sentry_issue_detail"](123, event=event_type)
        assert route.called is True

    assert issue_route.call_count == 3

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_project_id_cache_expiry(monkeypatch):
    _mock_scope(monkeypatch)
    client = SentryClient("token", org="instainstru")

    projects_route = respx.get(
        "https://sentry.io/api/0/organizations/instainstru/projects/"
    ).respond(200, json=[{"slug": "instainstru-api", "id": "42"}])

    await client._get_project_ids()
    client._project_ids_fetched_at = datetime.now(timezone.utc) - timedelta(hours=25)
    await client._get_project_ids()

    assert projects_route.call_count == 2

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_sentry_client_error_handling():
    client = SentryClient("token", org="instainstru")

    respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(401)
    with pytest.raises(SentryAuthError):
        await client._request("GET", "/organizations/instainstru/issues/")

    respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(403)
    with pytest.raises(SentryAuthError):
        await client._request("GET", "/organizations/instainstru/issues/")

    respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(404)
    with pytest.raises(SentryNotFoundError):
        await client._request("GET", "/organizations/instainstru/issues/")

    respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(
        429, headers={"Retry-After": "120"}
    )
    with pytest.raises(SentryRateLimitError) as exc:
        await client._request("GET", "/organizations/instainstru/issues/")
    assert exc.value.retry_after == 120

    await client.aclose()


def test_redact_email_edge_cases():
    assert sentry_tools._redact_email("a@example.com") == "a***@example.com"
    assert sentry_tools._redact_email("ab@example.com") == "a***@example.com"
    assert sentry_tools._redact_email("@example.com") == "***@example.com"
    assert sentry_tools._redact_email("notanemail") == "notanemail"
    assert sentry_tools._redact_email("") == ""


def test_secret_value_and_parse_retry_after():
    assert _secret_value(None) == ""
    assert _secret_value("token") == "token"
    assert _secret_value(SecretStr("secret")) == "secret"
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("abc") is None


def test_decode_response_and_extract_error_message():
    response = httpx.Response(200, content=b"not-json")
    assert _decode_response(response) == {}
    assert _extract_error_message(response) == "not-json"

    response = httpx.Response(400, json={"detail": "bad request"})
    assert _extract_error_message(response) == "bad request"

    response = httpx.Response(400, json={"errors": [{"message": "nope"}]})
    assert _extract_error_message(response) == "nope"

    response = httpx.Response(400, json=["problem"])
    assert _extract_error_message(response) == "problem"


@pytest.mark.asyncio
async def test_request_not_configured():
    client = SentryClient("", org="instainstru")
    with pytest.raises(SentryNotConfiguredError):
        await client._request("GET", "/organizations/instainstru/issues/")
    await client.aclose()


@pytest.mark.asyncio
async def test_request_timeout_and_http_error():
    client = SentryClient("token", org="instainstru")

    async def raise_timeout(*_args, **_kwargs):
        raise httpx.ReadTimeout("timeout", request=httpx.Request("GET", "https://sentry.io"))

    client.http.request = raise_timeout
    with pytest.raises(SentryConnectionError):
        await client._request("GET", "/organizations/instainstru/issues/")

    async def raise_http_error(*_args, **_kwargs):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://sentry.io"))

    client.http.request = raise_http_error
    with pytest.raises(SentryConnectionError):
        await client._request("GET", "/organizations/instainstru/issues/")

    await client.aclose()


@pytest.mark.asyncio
async def test_request_merges_headers():
    client = SentryClient("token", org="instainstru")
    response = httpx.Response(200, json={"ok": True})
    client.http.request = AsyncMock(return_value=response)

    await client._request("GET", "/organizations/instainstru/issues/", headers={"X-Test": "1"})
    headers = client.http.request.call_args.kwargs["headers"]
    assert headers["X-Test"] == "1"
    assert headers["Accept"] == "application/json"
    assert headers["Authorization"].startswith("Bearer ")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_request_400_raises_request_error():
    client = SentryClient("token", org="instainstru")
    respx.get("https://sentry.io/api/0/organizations/instainstru/issues/").respond(
        400, json={"detail": "bad request"}
    )
    with pytest.raises(SentryRequestError) as exc:
        await client._request("GET", "/organizations/instainstru/issues/")
    assert exc.value.status_code == 400
    assert "bad request" in str(exc.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_project_id_cache_hit(monkeypatch):
    client = SentryClient("token", org="instainstru")
    client._project_ids = {"instainstru-api": 101}
    client._project_ids_fetched_at = datetime.now(timezone.utc)
    mock_request = AsyncMock()
    monkeypatch.setattr(client, "_request", mock_request)

    result = await client._get_project_ids()
    assert result["instainstru-api"] == 101
    mock_request.assert_not_called()

    await client.aclose()


@pytest.mark.asyncio
async def test_project_id_parsing_skips_invalid(monkeypatch):
    client = SentryClient("token", org="instainstru")
    data = [
        {"slug": "instainstru-api", "id": "42"},
        {"slug": "instainstru-web", "id": "bad"},
        "not-a-dict",
    ]
    monkeypatch.setattr(client, "_request", AsyncMock(return_value=data))

    result = await client._get_project_ids()
    assert result == {"instainstru-api": 42}

    await client.aclose()


@pytest.mark.asyncio
async def test_resolve_project_param_errors(monkeypatch):
    client = SentryClient("token", org="instainstru")
    with pytest.raises(ValueError):
        await client._resolve_project_param("unknown")

    monkeypatch.setattr(client, "_get_project_ids", AsyncMock(return_value={}))
    with pytest.raises(ValueError):
        await client._resolve_project_param("api")

    await client.aclose()


@pytest.mark.asyncio
async def test_issues_cache_expiry():
    client = SentryClient("token", org="instainstru")
    cache_key = "sentry:issues:test"
    expired = datetime.now(timezone.utc) - timedelta(minutes=5)
    client._issues_cache[cache_key] = (expired, [{"id": 1}])

    assert client._get_cached_issues(cache_key) is None
    assert cache_key not in client._issues_cache

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_resolve_event_id_and_project_event():
    client = SentryClient("token", org="instainstru")
    respx.get("https://sentry.io/api/0/organizations/instainstru/eventids/evt-1/").respond(
        200, json={"projectSlug": "instainstru-api"}
    )
    respx.get("https://sentry.io/api/0/projects/instainstru/instainstru-api/events/evt-1/").respond(
        200, json={"id": "evt-1"}
    )

    resolved = await client.resolve_event_id("evt-1")
    event = await client.get_project_event("instainstru-api", "evt-1")
    assert resolved["projectSlug"] == "instainstru-api"
    assert event["id"] == "evt-1"

    await client.aclose()


def test_validate_choice_and_issue_id_helpers():
    assert sentry_tools._validate_choice("project", "API", {"api", "web"}) == "api"
    assert sentry_tools._validate_issue_id("123") == 123
    with pytest.raises(ValueError):
        sentry_tools._validate_choice("project", "bad", {"api"})


def test_build_issue_query_variants():
    assert sentry_tools._build_issue_query("unresolved", None) == "is:unresolved"
    assert (
        sentry_tools._build_issue_query("resolved", "error.type:RuntimeError")
        == "is:resolved error.type:RuntimeError"
    )
    assert sentry_tools._build_issue_query("all", "user.email:test") == "user.email:test"


def test_safe_int_and_format_issue_helpers():
    assert sentry_tools._safe_int("bad") == 0
    issue = {"id": "abc", "project": "instainstru-api", "count": "2", "userCount": "3"}
    formatted = sentry_tools._format_issue(issue)
    assert formatted["id"] == "abc"
    assert formatted["project"] == "instainstru-api"
    assert formatted["count"] == 2
    assert formatted["user_count"] == 3


def test_extract_message_and_tags_helpers():
    event = {"logentry": {"message": "fallback message"}}
    assert sentry_tools._extract_message(event) == "fallback message"
    assert sentry_tools._extract_message({}) is None

    tags_dict = {"browser": "Chrome"}
    assert sentry_tools._normalize_tags(tags_dict) == tags_dict

    tags_list = [{"key": "os", "value": "macOS"}]
    assert sentry_tools._normalize_tags(tags_list) == {"os": "macOS"}

    assert sentry_tools._normalize_tags("invalid") == {}


def test_redact_user_and_headers_helpers():
    assert sentry_tools._redact_user("not-a-dict") is None
    assert sentry_tools._redact_user({}) is None
    assert sentry_tools._redact_user({"id": "u1"}) == {"id": "u1"}

    headers_list = [["X-Test", "1"], {"name": "X-Other", "value": "2"}]
    normalized = sentry_tools._normalize_headers(headers_list)
    assert normalized["X-Test"] == "1"
    assert normalized["X-Other"] == "2"
    assert sentry_tools._normalize_headers("bad") == {}


def test_extract_request_and_stacktrace_helpers():
    assert sentry_tools._extract_request("bad") is None

    request = {"method": "GET", "url": "/health", "headers": [["X-Test", "1"]]}
    extracted = sentry_tools._extract_request(request)
    assert extracted["method"] == "GET"
    assert extracted["url"] == "/health"
    assert extracted["headers"]["X-Test"] == "1"

    event = {
        "entries": [
            "not-a-dict",
            {
                "type": "stacktrace",
                "data": {
                    "frames": [
                        "not-a-frame",
                        {"lineno": 12, "context_line": "line"},
                    ]
                },
            },
        ]
    }
    stacktrace = sentry_tools._extract_stacktrace(event, max_frames=5)
    assert "File" in stacktrace
    assert "<unknown>" in stacktrace

    frames = sentry_tools._find_stacktrace_frames(event)
    assert isinstance(frames, list)

    empty_frames = sentry_tools._find_stacktrace_frames(
        {"entries": [{"type": "exception", "data": {"values": ["bad"]}}]}
    )
    assert empty_frames == []


def test_issue_reference_and_handle_error_helpers():
    ref = sentry_tools._build_issue_reference("abc", "instainstru")
    assert ref["id"] == "abc"

    assert (
        sentry_tools._handle_error(SentryNotConfiguredError("x"))["error"]
        == "sentry_not_configured"
    )
    assert sentry_tools._handle_error(SentryAuthError("x"))["error"] == "sentry_auth_failed"
    rate = sentry_tools._handle_error(SentryRateLimitError("x", retry_after=5))
    assert rate["retry_after_seconds"] == 5
    assert sentry_tools._handle_error(SentryNotFoundError("x"))["error"] == "sentry_not_found"
    assert (
        sentry_tools._handle_error(SentryConnectionError("x"))["error"]
        == "sentry_connection_failed"
    )
    req = sentry_tools._handle_error(SentryRequestError("x", status_code=400))
    assert req["status_code"] == 400
    assert sentry_tools._handle_error(PermissionError("nope"))["error"] == "insufficient_scope"
    assert sentry_tools._handle_error(ValueError("bad"))["error"] == "invalid_request"
    assert sentry_tools._handle_error(Exception("boom"))["error"] == "unknown_error"


def test_require_scope_variants(monkeypatch):
    _mock_scope_with(monkeypatch, {"method": "jwt", "claims": {}})
    sentry_tools._require_scope("mcp:read")

    _mock_scope_with(monkeypatch, {"method": "jwt", "claims": {"scope": "mcp:write"}})
    sentry_tools._require_scope("mcp:write")

    _mock_scope_with(monkeypatch, {"method": "jwt", "claims": {}})
    with pytest.raises(PermissionError):
        sentry_tools._require_scope("mcp:write")


@pytest.mark.asyncio
async def test_tool_validation_errors(monkeypatch):
    _mock_scope(monkeypatch)
    fake = FakeSentryClient()
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_issues_top"](limit=0)
    assert result["error"] == "invalid_request"

    result = await tools["instainstru_sentry_issue_detail"](123, max_frames=0)
    assert result["error"] == "invalid_request"

    result = await tools["instainstru_sentry_event_lookup"]("  ")
    assert result["error"] == "invalid_request"


@pytest.mark.asyncio
async def test_event_lookup_missing_project_slug(monkeypatch):
    _mock_scope(monkeypatch)
    fake = FakeSentryClient(resolved={})
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_event_lookup"]("evt-1")
    assert result["error"] == "invalid_request"


@pytest.mark.asyncio
async def test_event_lookup_group_id_not_found(monkeypatch):
    _mock_scope(monkeypatch)

    class MissingIssueClient(FakeSentryClient):
        async def get_issue(self, issue_id: int):
            raise SentryNotFoundError("missing")

    fake = MissingIssueClient(
        resolved={"projectSlug": "instainstru-api", "groupId": 999},
        project_event=_sample_event(),
    )
    mcp = FastMCP("test")
    tools = sentry_tools.register_tools(mcp, fake)

    result = await tools["instainstru_sentry_event_lookup"]("evt-1")
    assert result["found"] is True
