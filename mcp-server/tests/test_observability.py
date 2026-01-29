from datetime import datetime

import httpx
import pytest
import respx
from fastmcp import FastMCP
from instainstru_mcp.config import Settings
from instainstru_mcp.grafana_client import (
    GrafanaAuthError,
    GrafanaCloudClient,
    GrafanaConnectionError,
    GrafanaNotConfiguredError,
    GrafanaNotFoundError,
    GrafanaRateLimitError,
    GrafanaRequestError,
    _secret_value,
)
from instainstru_mcp.tools import observability
from pydantic import SecretStr


@pytest.mark.asyncio
@respx.mock
async def test_prometheus_query_success():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
        grafana_prometheus_datasource_uid="prometheus",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/datasources/proxy/uid/prometheus/api/v1/query").respond(
        200,
        json={
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"job": "instainstru-api"},
                        "value": [1700000000, "1"],
                    }
                ],
            },
        },
    )

    result = await client.query_prometheus("up")
    assert result["result_type"] == "vector"
    assert result["results"][0]["metric"]["job"] == "instainstru-api"
    assert result["results"][0]["value"][1] == "1"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_prometheus_query_range_success():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
        grafana_prometheus_datasource_uid="prometheus",
    )
    client = GrafanaCloudClient(settings)

    respx.get(
        "https://grafana.test/api/datasources/proxy/uid/prometheus/api/v1/query_range"
    ).respond(
        200,
        json={
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"job": "instainstru-api"},
                        "values": [[1700000000, "1"]],
                    }
                ],
            },
        },
    )

    result = await client.query_prometheus_range(
        "up",
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T00:10:00Z",
    )
    assert result["result_type"] == "matrix"
    assert result["results"][0]["values"][0][1] == "1"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_prometheus_query_error_payload_raises():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
        grafana_prometheus_datasource_uid="prometheus",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/datasources/proxy/uid/prometheus/api/v1/query").respond(
        200, json={"status": "error", "error": "parse error"}
    )

    with pytest.raises(GrafanaRequestError, match="parse error"):
        await client.query_prometheus("up")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_list_dashboards_structured():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/search").respond(
        200,
        json=[
            {"uid": "instainstru-api-health", "title": "API Health", "folderTitle": "InstaInstru"},
            {"uid": "bgc-overview", "title": "BGC Overview", "folderTitle": "InstaInstru"},
        ],
    )

    dashboards = await client.list_dashboards()
    assert dashboards[0]["uid"] == "instainstru-api-health"
    assert dashboards[1]["title"] == "BGC Overview"
    assert dashboards[0]["folder"] == "InstaInstru"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_alerts_list_filters_state():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/alertmanager/grafana/api/v2/alerts").respond(
        200,
        json=[
            {"labels": {"alertname": "HighLatency"}, "status": {"state": "firing"}},
            {"labels": {"alertname": "LowTraffic"}, "status": {"state": "inactive"}},
        ],
    )

    alerts = await client.list_alerts(state="firing")
    assert len(alerts) == 1
    assert alerts[0]["name"] == "HighLatency"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_silences_filter_active_only():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/alertmanager/grafana/api/v2/silences").respond(
        200,
        json=[
            {"id": "s1", "status": {"state": "active"}, "comment": "noise"},
            {"id": "s2", "status": {"state": "expired"}, "comment": "old"},
        ],
    )

    silences = await client.list_silences(active_only=True)
    assert len(silences) == 1
    assert silences[0]["id"] == "s1"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_delete_silence_calls_endpoint():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    route = respx.delete("https://grafana.test/api/alertmanager/grafana/api/v2/silence/s1").respond(
        200
    )

    assert await client.delete_silence("s1") is True
    assert route.called is True

    await client.aclose()


@pytest.mark.asyncio
async def test_create_silence_rejects_long_duration():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    with pytest.raises(GrafanaRequestError, match="silence_duration_exceeds_24h"):
        await client.create_silence(
            matchers=[{"name": "alertname", "value": "HighLatency"}],
            duration_minutes=2000,
            comment="too long",
            created_by="tester",
        )

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_create_silence_returns_id_and_times():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.post("https://grafana.test/api/alertmanager/grafana/api/v2/silences").respond(
        200, json={"silenceID": "sil-123"}
    )

    result = await client.create_silence(
        matchers=[{"name": "alertname", "value": "HighLatency"}],
        duration_minutes=30,
        comment="investigating",
        created_by="tester",
    )
    assert result["silence_id"] == "sil-123"
    assert "starts_at" in result
    assert "ends_at" in result

    await client.aclose()


@pytest.mark.asyncio
async def test_dashboard_panels_extracts_nested_queries(monkeypatch):
    class FakeGrafana:
        async def get_dashboard(self, _uid):
            return {
                "title": "API Health",
                "panels": [
                    {
                        "type": "row",
                        "panels": [
                            {"id": 1, "title": "Up", "type": "stat", "targets": [{"expr": "up"}]}
                        ],
                    },
                    {
                        "id": 2,
                        "title": "Errors",
                        "type": "timeseries",
                        "targets": [{"expr": "rate(errors[5m])"}],
                    },
                ],
            }

    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)

    mcp = FastMCP("test")
    tools = observability.register_tools(mcp, FakeGrafana())

    result = await tools["instainstru_dashboard_panels"]("instainstru-api-health")
    assert result["count"] == 2
    assert result["panels"][0]["queries"] == ["up"]
    assert "rate(errors[5m])" in result["panels"][1]["queries"]


@pytest.mark.asyncio
async def test_prometheus_query_range_relative_times(monkeypatch):
    captured: dict[str, str] = {}

    class FakeGrafana:
        async def query_prometheus_range(self, query, start, end, step="60s"):
            captured["start"] = start
            captured["end"] = end
            return {"query": query, "result_type": "matrix", "results": []}

    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)

    mcp = FastMCP("test")
    tools = observability.register_tools(mcp, FakeGrafana())

    result = await tools["instainstru_prometheus_query_range"]("up", start="1h")
    assert result["result_type"] == "matrix"
    start_dt = datetime.fromisoformat(captured["start"])
    end_dt = datetime.fromisoformat(captured["end"])
    assert end_dt > start_dt


@pytest.mark.asyncio
async def test_prometheus_query_tool_resolves_time(monkeypatch):
    captured: dict[str, str | None] = {}

    class FakeGrafana:
        async def query_prometheus(self, query, time=None):
            captured["time"] = time
            return {"query": query, "result_type": "vector", "results": []}

    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)

    mcp = FastMCP("test")
    tools = observability.register_tools(mcp, FakeGrafana())

    result = await tools["instainstru_prometheus_query"]("up", time="2026-01-01T00:00:00Z")
    assert result["result_type"] == "vector"
    assert captured["time"] is not None


@pytest.mark.asyncio
async def test_alert_silence_requires_write_scope(monkeypatch):
    class FakeGrafana:
        async def create_silence(self, **_kwargs):
            return {"silence_id": "sil-1"}

    def fake_request():
        class Dummy:
            scope = {"auth": {"claims": {"scope": "mcp:read"}}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)

    mcp = FastMCP("test")
    tools = observability.register_tools(mcp, FakeGrafana())

    result = await tools["instainstru_alert_silence"](
        matchers=[{"name": "alertname", "value": "HighLatency", "isRegex": False}],
        duration_minutes=30,
        comment="investigating",
    )

    assert result["error"] == "insufficient_scope"


@pytest.mark.asyncio
async def test_grafana_not_configured(monkeypatch):
    settings = Settings(grafana_cloud_url="", grafana_cloud_api_key="")
    grafana = GrafanaCloudClient(settings)

    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)

    mcp = FastMCP("test")
    tools = observability.register_tools(mcp, grafana)

    result = await tools["instainstru_dashboards_list"]()
    assert result["error"] == "grafana_not_configured"

    await grafana.aclose()


@pytest.mark.asyncio
async def test_alerts_and_silences_tools_success(monkeypatch):
    class FakeGrafana:
        async def list_alerts(self, state=None):
            return [{"name": "HighLatency", "state": state or "firing"}]

        async def list_silences(self, active_only=True):
            return [{"id": "sil-1", "status": "active"}] if active_only else []

        async def list_dashboards(self):
            return [{"uid": "dash-1"}]

    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)

    mcp = FastMCP("test")
    tools = observability.register_tools(mcp, FakeGrafana())

    alerts = await tools["instainstru_alerts_list"]()
    assert alerts["count"] == 1
    silences = await tools["instainstru_silences_list"]()
    assert silences["count"] == 1
    dashboards = await tools["instainstru_dashboards_list"]()
    assert dashboards["count"] == 1


def test_handle_error_maps_grafana_errors():
    result = observability._handle_error(GrafanaNotConfiguredError("missing"))
    assert result["error"] == "grafana_not_configured"

    result = observability._handle_error(GrafanaAuthError("nope"))
    assert result["error"] == "grafana_auth_failed"

    result = observability._handle_error(GrafanaRateLimitError("rate", retry_after=12))
    assert result["retry_after_seconds"] == 12

    result = observability._handle_error(GrafanaNotFoundError("missing"))
    assert result["error"] == "grafana_not_found"

    result = observability._handle_error(GrafanaConnectionError("boom"))
    assert result["error"] == "grafana_connection_failed"

    result = observability._handle_error(GrafanaRequestError("bad", status_code=500))
    assert result["status_code"] == 500


def test_handle_error_maps_validation_and_permissions():
    result = observability._handle_error(PermissionError("nope"))
    assert result["error"] == "insufficient_scope"

    result = observability._handle_error(ValueError("bad"))
    assert result["error"] == "invalid_request"

    result = observability._handle_error(RuntimeError("unknown"))
    assert result["error"] == "unknown_error"


def test_grafana_client_configured_and_auth_header():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)
    assert client.configured is True
    assert client._auth_header() == {"Authorization": "Bearer token"}


def test_grafana_client_secret_value_handles_secretstr():
    assert _secret_value(None) == ""
    assert _secret_value("token") == "token"
    assert _secret_value(SecretStr("secret")) == "secret"


@pytest.mark.asyncio
async def test_grafana_request_not_configured():
    settings = Settings(grafana_cloud_url="", grafana_cloud_api_key="")
    client = GrafanaCloudClient(settings)

    with pytest.raises(GrafanaNotConfiguredError):
        await client._request("GET", "/api/search")

    await client.aclose()


@pytest.mark.asyncio
async def test_grafana_request_timeout_and_connection_errors(monkeypatch):
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    async def _timeout(*_args, **_kwargs):
        raise httpx.TimeoutException("timeout")

    async def _http_error(*_args, **_kwargs):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(client.http, "request", _timeout)
    with pytest.raises(GrafanaConnectionError, match="grafana_timeout"):
        await client._request("GET", "/api/search")

    monkeypatch.setattr(client.http, "request", _http_error)
    with pytest.raises(GrafanaConnectionError, match="grafana_connection_failed"):
        await client._request("GET", "/api/search")

    await client.aclose()


def test_extract_panels_skips_non_dict_targets():
    panels = [
        "not-a-panel",
        {
            "id": 1,
            "title": "Panel",
            "type": "stat",
            "targets": ["bad-target", {"rawQuery": "up"}],
        },
    ]
    extracted = observability._extract_panels(panels)
    assert extracted[0]["queries"] == ["up"]


def test_resolve_relative_time_invalid_raises():
    now = datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="Invalid time format"):
        observability._resolve_relative_time("bad", now)


def test_resolve_time_parses_iso_strings():
    result = observability._resolve_time("2026-01-01T00:00:00")
    assert result.endswith("+00:00")

    result_z = observability._resolve_time("2026-01-01T00:00:00Z")
    assert result_z.endswith("+00:00")

    assert observability._resolve_time(None) is None


def test_require_scope_accepts_scp_claim(monkeypatch):
    def fake_request():
        class Dummy:
            scope = {"auth": {"claims": {"scp": "mcp:read mcp:write"}}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)
    observability._require_scope("mcp:read")


def test_require_scope_allows_read_without_scope_for_oauth(monkeypatch):
    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "workos"}}

        return Dummy()

    monkeypatch.setattr(observability, "get_http_request", fake_request)
    observability._require_scope("mcp:read")


@pytest.mark.asyncio
@respx.mock
async def test_grafana_request_auth_error():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/search").respond(401)
    with pytest.raises(GrafanaAuthError):
        await client._request("GET", "/api/search")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_grafana_request_not_found_error():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/search").respond(404)
    with pytest.raises(GrafanaNotFoundError):
        await client._request("GET", "/api/search")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_grafana_request_rate_limit_parses_retry_after():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/search").respond(429, headers={"Retry-After": "30"})
    with pytest.raises(GrafanaRateLimitError) as exc:
        await client._request("GET", "/api/search")
    assert exc.value.retry_after == 30

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_grafana_request_rate_limit_non_numeric_retry():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/search").respond(429, headers={"Retry-After": "soon"})
    with pytest.raises(GrafanaRateLimitError) as exc:
        await client._request("GET", "/api/search")
    assert exc.value.retry_after is None

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_grafana_request_error_message_from_payload():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/search").respond(500, json={"message": "bad"})
    with pytest.raises(GrafanaRequestError, match="bad"):
        await client._request("GET", "/api/search")

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_grafana_request_non_json_fallback():
    settings = Settings(
        grafana_cloud_url="https://grafana.test",
        grafana_cloud_api_key="token",
    )
    client = GrafanaCloudClient(settings)

    respx.get("https://grafana.test/api/search").respond(200, text="not-json")
    result = await client._request("GET", "/api/search")
    assert result["status_code"] == 200
    assert result["text"] == "not-json"

    await client.aclose()
