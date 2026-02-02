from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from fastmcp import FastMCP
from instainstru_mcp.tools import command_center


def _mock_scope(monkeypatch):
    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(command_center, "get_http_request", fake_request)


class FakeGrafana:
    def __init__(
        self,
        *,
        raise_on_query: bool = False,
        latency_sec: float = 0.2,
        error_rate: float = 0.001,
        rps: float = 3.5,
        alerts: list[dict] | None = None,
    ) -> None:
        self.raise_on_query = raise_on_query
        self.latency_sec = latency_sec
        self.error_rate = error_rate
        self.rps = rps
        self.alerts = alerts or []

    async def query_prometheus(self, query: str, time: str | None = None) -> dict:
        if self.raise_on_query:
            raise RuntimeError("prometheus_down")
        if query.startswith("up"):
            return {"results": [{"metric": {"instance": "api-1"}, "value": [1700000000, "1"]}]}
        if "http_request_duration_seconds_bucket" in query:
            value = str(self.latency_sec)
        elif "5.." in query and "/" in query:
            value = str(self.error_rate)
        else:
            value = str(self.rps)
        return {"results": [{"metric": {}, "value": [1700000000, value]}]}

    async def list_alerts(self, state: str | None = None) -> list[dict]:
        return self.alerts


class FakeClient:
    def __init__(self, *, oldest_payout_date: str | None = None) -> None:
        self.oldest_payout_date = oldest_payout_date

    async def get_celery_workers(self) -> dict:
        return {
            "summary": {
                "total_workers": 2,
                "online_workers": 2,
                "offline_workers": 0,
                "total_active_tasks": 0,
            },
            "workers": [],
        }

    async def get_celery_queues(self) -> dict:
        return {"total_depth": 0, "queues": []}

    async def get_celery_failed_tasks(self, limit: int = 50) -> dict:
        return {"count": 0, "failed_tasks": []}

    async def get_celery_payment_health(self) -> dict:
        return {
            "healthy": True,
            "issues": [],
            "pending_authorizations": 0,
            "overdue_authorizations": 0,
            "pending_captures": 0,
            "failed_payments_24h": 0,
            "last_task_runs": [],
        }

    async def get_payment_pipeline(self) -> dict:
        return {
            "pending_authorization": 0,
            "authorized": 0,
            "pending_capture": 0,
            "captured": 0,
            "failed": 0,
            "refunded": 0,
            "overdue_authorizations": 0,
            "overdue_captures": 0,
            "total_captured_cents": 0,
            "total_refunded_cents": 0,
            "net_revenue_cents": 0,
            "platform_fees_cents": 0,
            "instructor_payouts_cents": 0,
        }

    async def get_pending_payouts(self, limit: int = 20) -> dict:
        payouts = []
        if self.oldest_payout_date:
            payouts.append(
                {
                    "instructor_id": "inst-1",
                    "instructor_name": "Sam C.",
                    "pending_amount_cents": 12000,
                    "completed_lessons": 2,
                    "oldest_pending_date": self.oldest_payout_date,
                    "stripe_connected": True,
                }
            )
        return {"payouts": payouts, "total_pending_cents": 0, "instructor_count": 0}

    async def get_booking_summary(self, period: str = "today") -> dict:
        return {
            "summary": {
                "period": period,
                "total_bookings": 3,
                "by_status": {"confirmed": 3},
                "total_revenue_cents": 45000,
                "avg_booking_value_cents": 15000,
                "new_students": 2,
                "repeat_students": 1,
                "top_categories": [],
            }
        }

    async def get_top_queries(self, **_kwargs) -> dict:
        return {"data": {"queries": [], "total_searches": 0}, "meta": {}}

    async def get_zero_results(self, **_kwargs) -> dict:
        return {
            "data": {
                "queries": [],
                "total_zero_result_searches": 0,
                "zero_result_rate": 0.0,
            },
            "meta": {},
        }


class FakeSentry:
    def __init__(self, issues: list[dict] | None = None) -> None:
        self.issues = issues or []
        self.org = "instainstru"

    async def list_issues(self, **_kwargs) -> list[dict]:
        return self.issues


class FakeAxiom:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.raise_error = raise_error

    async def query_apl(self, apl: str) -> dict:
        if self.raise_error:
            raise RuntimeError("axiom_down")
        if "summarize spans" in apl:
            return {
                "tables": [
                    {
                        "name": "ingestion",
                        "columns": [
                            {"name": "service.name"},
                            {"name": "spans"},
                            {"name": "traces"},
                            {"name": "error_spans"},
                        ],
                        "rows": [["api", 120, 40, 0]],
                    }
                ]
            }
        if "summarize requests" in apl:
            return {
                "tables": [
                    {
                        "name": "root",
                        "columns": [
                            {"name": "service.name"},
                            {"name": "requests"},
                            {"name": "errors"},
                            {"name": "p50"},
                            {"name": "p95"},
                            {"name": "p99"},
                        ],
                        "rows": [["api", 50, 0, 0.1, 0.2, 0.3]],
                    }
                ]
            }
        return {
            "tables": [
                {
                    "name": "slow",
                    "columns": [
                        {"name": "service.name"},
                        {"name": "name"},
                        {"name": "requests"},
                        {"name": "p99"},
                    ],
                    "rows": [["api", "GET /", 10, 0.5]],
                }
            ]
        }


def test_delta_calculation():
    result = command_center.calculate_delta(10, 5)
    assert result["delta_abs"] == 5
    assert result["delta_pct"] == 1.0

    zero = command_center.calculate_delta(5, 0)
    assert zero["delta_pct"] is None
    assert zero["notes"] == "prev is zero"

    missing = command_center.calculate_delta(None, 1)
    assert missing["notes"] == "no comparison data"


def test_calculate_status():
    assert command_center.calculate_status([{"status": "ok"}]) == "ok"
    assert command_center.calculate_status([{"status": "warning"}]) == "warning"
    assert command_center.calculate_status([{"status": "unknown"}]) == "unknown"
    assert command_center.calculate_status([{"status": "critical"}]) == "critical"


def test_threshold_evaluation():
    assert command_center._evaluate_threshold(None, 1, 2) == "unknown"
    assert command_center._evaluate_threshold(0.5, 1, 2) == "ok"
    assert command_center._evaluate_threshold(1.5, 1, 2) == "warning"
    assert command_center._evaluate_threshold(2.5, 1, 2) == "critical"


def test_overall_severity():
    status, severity = command_center.calculate_overall("critical", "ok", "ok")
    assert status == "critical"
    assert severity == 2


@pytest.mark.asyncio
@respx.mock
async def test_axiom_client_query_success():
    client = command_center.AxiomClient(token="token", base_url="https://axiom.test")
    route = respx.post("https://axiom.test/v1/datasets/_apl").respond(200, json={"tables": []})

    result = await client.query_apl("['logs'] | count")
    assert route.called
    assert result == {"tables": []}
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_axiom_client_invalid_json():
    client = command_center.AxiomClient(token="token", base_url="https://axiom.test")
    respx.post("https://axiom.test/v1/datasets/_apl").respond(200, content=b"not-json")

    result = await client.query_apl("['logs'] | count")
    assert result == {}
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("status_code", "exc_type"),
    [
        (401, command_center.AxiomAuthError),
        (429, command_center.AxiomRateLimitError),
        (500, command_center.AxiomRequestError),
    ],
)
async def test_axiom_client_error_status(status_code, exc_type):
    client = command_center.AxiomClient(token="token", base_url="https://axiom.test")
    respx.post("https://axiom.test/v1/datasets/_apl").respond(status_code)

    with pytest.raises(exc_type):
        await client.query_apl("['logs'] | count")
    await client.aclose()


@pytest.mark.asyncio
async def test_axiom_client_not_configured():
    client = command_center.AxiomClient(token="")
    with pytest.raises(command_center.AxiomNotConfiguredError):
        await client.query_apl("['logs'] | count")
    await client.aclose()


@pytest.mark.asyncio
async def test_axiom_client_request_exceptions(monkeypatch):
    client = command_center.AxiomClient(token="token", base_url="https://axiom.test")

    async def raise_timeout(*_args, **_kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(client.http, "request", raise_timeout)
    with pytest.raises(command_center.AxiomConnectionError):
        await client.query_apl("['logs'] | count")

    async def raise_http_error(*_args, **_kwargs):
        raise httpx.HTTPError("http")

    monkeypatch.setattr(client.http, "request", raise_http_error)
    with pytest.raises(command_center.AxiomConnectionError):
        await client.query_apl("['logs'] | count")

    await client.aclose()


def test_require_scope_branches(monkeypatch):
    def fake_request_jwt():
        class Dummy:
            scope = {"auth": {"method": "jwt", "claims": {}}}

        return Dummy()

    monkeypatch.setattr(command_center, "get_http_request", fake_request_jwt)
    command_center._require_scope("mcp:read")

    def fake_request_none():
        class Dummy:
            scope = {"auth": {"method": "oauth", "claims": {}}}

        return Dummy()

    monkeypatch.setattr(command_center, "get_http_request", fake_request_none)
    with pytest.raises(PermissionError):
        command_center._require_scope("mcp:write")


def test_normalize_and_sanitize_helpers():
    with pytest.raises(ValueError):
        command_center._normalize_duration("bad", fallback="30m")

    assert (
        command_center._sanitize_dataset("bad dataset!", fallback="instainstru-logs")
        == "instainstru-logs"
    )


def test_safe_float_and_scalar_helpers():
    assert command_center._safe_float("3.5") == 3.5
    assert command_center._safe_float("not-a-number") is None
    assert command_center._safe_float(float("nan")) is None
    assert command_center._safe_float(float("inf")) is None

    assert command_center._extract_scalar([]) is None
    assert (
        command_center._extract_scalar(
            [{"value": [0, "1"]}, {"value": [0, "2"]}, {"value": [0, "3"]}]
        )
        == 6
    )


def test_extract_uptime_branches():
    unknown = command_center._extract_uptime([])
    assert unknown["status"] == "unknown"

    warning = command_center._extract_uptime(
        [
            {"metric": {"instance": "a"}, "value": [0, "0"]},
            {"metric": {"instance": "b"}, "value": [0, "1"]},
            {"metric": {"instance": "c"}, "value": None},
        ]
    )
    assert warning["status"] == "warning"

    critical = command_center._extract_uptime([{"metric": {"instance": "a"}, "value": [0, "0"]}])
    assert critical["status"] == "critical"


def test_parse_datetime_variants():
    assert command_center._parse_datetime(None) is None
    assert command_center._parse_datetime("   ") is None
    assert command_center._parse_datetime("invalid") is None

    with_z = command_center._parse_datetime("2026-01-01T00:00:00Z")
    assert with_z is not None and with_z.tzinfo is not None

    naive = command_center._parse_datetime("2026-01-01T00:00:00")
    assert naive is not None and naive.tzinfo is not None


def test_tabular_rows_variants():
    assert command_center._tabular_rows({}) == []
    assert command_center._tabular_rows({"tables": [{"columns": "bad", "rows": []}]}) == []

    rows = command_center._tabular_rows(
        {"tables": [{"columns": [{"name": "a"}], "rows": [[1], "bad"]}]}
    )
    assert rows[0]["a"] == 1

    fallback = command_center._tabular_rows(
        {"tables": [{"columns": [{"name": ""}], "rows": [[1]]}]}
    )
    assert fallback[0]["col_0"] == 1


def test_build_top_actions_branches():
    actions = command_center._build_top_actions(
        latency_status="critical",
        latency_value=1200.0,
        error_status="warning",
        error_value=0.05,
        alerts_count=2,
        celery_queue_status="warning",
        celery_failures_status="critical",
        payment_health_status="warning",
        pipeline_status="warning",
        payouts_status="critical",
        window="30m",
    )
    assert len(actions) == 5
    assert actions[0]["title"] == "Investigate latency spike"
    assert actions[1]["title"] == "Inspect elevated error rate"


@pytest.mark.asyncio
async def test_snapshot_returns_valid_schema(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = command_center.register_tools(
        mcp, FakeClient(), FakeGrafana(), FakeSentry(), FakeAxiom()
    )

    result = await tools["instainstru_command_center_snapshot"](env="production", window="30m")

    assert result["meta"]["schema_version"] == "1.0.0"
    assert result["overall"]["status"] in {"ok", "warning", "critical", "unknown"}
    assert "stability" in result
    assert "money" in result
    assert "growth" in result
    assert result["stability"]["checks"]["latency"]["status"] == "ok"


@pytest.mark.asyncio
async def test_snapshot_handles_prometheus_failure(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = command_center.register_tools(
        mcp, FakeClient(), FakeGrafana(raise_on_query=True), FakeSentry(), FakeAxiom()
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["stability"]["checks"]["latency"]["status"] == "unknown"
    assert result["stability"]["checks"]["errors"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_snapshot_handles_axiom_failure(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = command_center.register_tools(
        mcp, FakeClient(), FakeGrafana(), FakeSentry(), FakeAxiom(raise_error=True)
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["stability"]["tracing"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_pending_payouts_age_status(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    oldest = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
    tools = command_center.register_tools(
        mcp,
        FakeClient(oldest_payout_date=oldest),
        FakeGrafana(),
        FakeSentry(),
        FakeAxiom(),
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["money"]["pending_payouts"]["status"] == "critical"


@pytest.mark.asyncio
@pytest.mark.parametrize(("hours", "expected"), [(72, "warning"), (24, "ok")])
async def test_pending_payouts_age_levels(monkeypatch, hours, expected):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    oldest = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    tools = command_center.register_tools(
        mcp,
        FakeClient(oldest_payout_date=oldest),
        FakeGrafana(),
        FakeSentry(),
        FakeAxiom(),
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["money"]["pending_payouts"]["status"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("total", "offline", "expected"), [(2, 2, "critical"), (2, 1, "warning")])
async def test_worker_status_variants(monkeypatch, total, offline, expected):
    _mock_scope(monkeypatch)

    class WorkerClient(FakeClient):
        async def get_celery_workers(self) -> dict:
            return {
                "summary": {
                    "total_workers": total,
                    "online_workers": max(total - offline, 0),
                    "offline_workers": offline,
                    "total_active_tasks": 0,
                },
                "workers": [],
            }

    mcp = FastMCP("test")
    tools = command_center.register_tools(
        mcp, WorkerClient(), FakeGrafana(), FakeSentry(), FakeAxiom()
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["stability"]["celery"]["workers"]["status"] == expected


@pytest.mark.asyncio
async def test_snapshot_issue_branches(monkeypatch):
    _mock_scope(monkeypatch)

    class IssueClient(FakeClient):
        async def get_celery_workers(self) -> dict:
            return {
                "summary": {
                    "total_workers": 0,
                    "online_workers": 0,
                    "offline_workers": 0,
                    "total_active_tasks": 0,
                },
                "workers": [],
            }

        async def get_celery_queues(self) -> dict:
            return {"total_depth": None, "queues": []}

        async def get_celery_failed_tasks(self, limit: int = 50) -> dict:
            return {"count": None, "failed_tasks": []}

        async def get_celery_payment_health(self) -> dict:
            return {
                "healthy": False,
                "issues": [
                    {"severity": "warning", "message": "warn", "count": 1},
                    {"severity": "critical", "message": "crit", "count": 2},
                ],
            }

        async def get_payment_pipeline(self) -> dict:
            return {"overdue_authorizations": 2, "overdue_captures": 1}

        async def get_pending_payouts(self, limit: int = 20) -> dict:
            return {
                "payouts": [
                    {
                        "instructor_id": "inst-2",
                        "instructor_name": "Alex D.",
                        "pending_amount_cents": 5000,
                        "completed_lessons": 1,
                        "oldest_pending_date": "not-a-date",
                        "stripe_connected": True,
                    }
                ],
                "total_pending_cents": 5000,
                "instructor_count": 1,
            }

    grafana = FakeGrafana(
        latency_sec=2.0,
        error_rate=0.05,
        alerts=[{"state": "firing", "labels": {"alertname": "HighErrorRate"}}],
    )

    mcp = FastMCP("test")
    tools = command_center.register_tools(mcp, IssueClient(), grafana, FakeSentry(), FakeAxiom())

    result = await tools["instainstru_command_center_snapshot"](include_growth=False)

    assert result["growth"]["status"] == "skipped"
    assert result["stability"]["checks"]["latency"]["status"] == "critical"
    assert result["stability"]["checks"]["errors"]["status"] == "critical"
    assert result["stability"]["celery"]["workers"]["status"] == "unknown"
    assert result["money"]["payment_health"]["status"] == "critical"
    assert result["money"]["payments_pipeline"]["status"] == "warning"
    assert result["money"]["pending_payouts"]["status"] == "unknown"
    assert result["overall"]["summary"]


@pytest.mark.asyncio
async def test_snapshot_unknown_payment_payloads(monkeypatch):
    _mock_scope(monkeypatch)

    class EmptyPaymentClient(FakeClient):
        async def get_celery_payment_health(self) -> dict:
            return {}

        async def get_payment_pipeline(self) -> dict:
            return {}

    mcp = FastMCP("test")
    tools = command_center.register_tools(
        mcp, EmptyPaymentClient(), FakeGrafana(), FakeSentry(), FakeAxiom()
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["money"]["payment_health"]["status"] == "unknown"
    assert result["money"]["payments_pipeline"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_alerts_payload_non_list(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = command_center.register_tools(
        mcp,
        FakeClient(),
        FakeGrafana(alerts="bad"),
        FakeSentry(),
        FakeAxiom(),
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["stability"]["alerts"]["firing_count"] == 0


@pytest.mark.asyncio
async def test_payment_health_healthy_false_warning(monkeypatch):
    _mock_scope(monkeypatch)

    class WarningPaymentClient(FakeClient):
        async def get_celery_payment_health(self) -> dict:
            return {"healthy": False, "issues": []}

    mcp = FastMCP("test")
    tools = command_center.register_tools(
        mcp, WarningPaymentClient(), FakeGrafana(), FakeSentry(), FakeAxiom()
    )

    result = await tools["instainstru_command_center_snapshot"]()
    assert result["money"]["payment_health"]["status"] == "warning"
