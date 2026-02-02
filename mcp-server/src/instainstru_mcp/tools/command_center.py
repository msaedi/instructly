"""
Command Center Snapshot - Single view of production health.

Aggregates: Prometheus metrics, Axiom traces, Sentry issues, Celery status,
payment health, and business metrics into one structured response.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from ..client import InstaInstruClient
from ..clients.sentry_client import SentryClient
from ..grafana_client import GrafanaCloudClient
from . import sentry as sentry_tools

SCHEMA_VERSION = "1.0.0"
DEFAULT_WINDOW = "30m"
DEFAULT_COMPARE_OFFSET = "24h"

DURATION_RE = re.compile(r"^\d+(s|m|h|d|w)$")
DATASET_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

THRESHOLDS = {
    "latency_p99_ok": 400,  # ms
    "latency_p99_warn": 800,  # ms
    "error_rate_ok": 0.005,  # 0.5%
    "error_rate_warn": 0.02,  # 2%
    "celery_queue_warn": 50,
    "celery_queue_critical": 200,
    "celery_failures_warn": 1,
    "celery_failures_critical": 5,
    "payout_age_warn_hours": 48,
    "payout_age_critical_hours": 168,
}

logger = logging.getLogger(__name__)


class AxiomClientError(Exception):
    """Base error for Axiom API failures."""


class AxiomNotConfiguredError(AxiomClientError):
    """Raised when Axiom settings are missing."""


class AxiomAuthError(AxiomClientError):
    """Raised when Axiom rejects authentication."""


class AxiomRateLimitError(AxiomClientError):
    """Raised when Axiom API rate limits requests."""


class AxiomConnectionError(AxiomClientError):
    """Raised when Axiom cannot be reached."""


class AxiomRequestError(AxiomClientError):
    """Raised for non-auth Axiom errors."""


class AxiomClient:
    """Minimal Axiom client for running APL queries."""

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token or os.getenv("AXIOM_API_TOKEN") or ""
        base = base_url or os.getenv("AXIOM_API_URL") or "https://api.axiom.co"
        self.base_url = base.rstrip("/")
        self.http = http or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    @property
    def configured(self) -> bool:
        return bool(self.token.strip())

    def _auth_header(self) -> dict[str, str]:
        token = self.token.strip()
        if token.lower().startswith("bearer "):
            return {"Authorization": token}
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not self.configured:
            raise AxiomNotConfiguredError("axiom_not_configured")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **self._auth_header(),
        }
        try:
            response = await self.http.request(
                method,
                path,
                params=params,
                json=json,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise AxiomConnectionError("axiom_timeout") from exc
        except httpx.HTTPError as exc:
            raise AxiomConnectionError(f"axiom_connection_failed: {exc}") from exc

        if response.status_code in {401, 403}:
            logger.warning(
                "Axiom auth failed: status=%s, body=%s",
                response.status_code,
                (response.text or "")[:200],
            )
            raise AxiomAuthError("axiom_auth_failed")
        if response.status_code == 429:
            raise AxiomRateLimitError("axiom_rate_limited")
        if response.status_code >= 400:
            raise AxiomRequestError(f"axiom_error_{response.status_code}")

        try:
            return response.json()
        except ValueError:
            return {}

    async def query_apl(self, apl: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/datasets/_apl",
            params={"format": "tabular"},
            json={"apl": apl},
        )


def calculate_status(checks: list[dict[str, Any]]) -> str:
    """Aggregate check statuses: worst wins."""
    statuses = [c.get("status") for c in checks if c.get("status")]
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    if "unknown" in statuses:
        return "unknown"
    return "ok"


def calculate_overall(
    stability_status: str, money_status: str, growth_status: str
) -> tuple[str, int]:
    """Overall = max(stability, money). Growth is informational."""
    severity_map = {"ok": 0, "warning": 1, "critical": 2, "unknown": 1}
    severity = max(
        severity_map.get(stability_status, 1),
        severity_map.get(money_status, 1),
    )
    status = {0: "ok", 1: "warning", 2: "critical"}[severity]
    return status, severity


def calculate_delta(now_value: float | None, prev_value: float | None) -> dict[str, Any]:
    """Calculate absolute and percentage delta."""
    if prev_value is None or now_value is None:
        return {"delta_abs": None, "delta_pct": None, "notes": "no comparison data"}

    delta_abs = now_value - prev_value
    if abs(prev_value) < 1e-9:
        return {"delta_abs": delta_abs, "delta_pct": None, "notes": "prev is zero"}

    delta_pct = (now_value - prev_value) / abs(prev_value)
    return {"delta_abs": delta_abs, "delta_pct": delta_pct}


def _require_scope(required_scope: str) -> None:
    request = get_http_request()
    auth = getattr(request, "scope", {}).get("auth", {})
    method = auth.get("method") if isinstance(auth, dict) else None
    if method == "simple_token":
        return
    claims = auth.get("claims", {}) if isinstance(auth, dict) else {}
    scope_value = ""
    if isinstance(claims, dict):
        scope_value = claims.get("scope") or claims.get("scp") or ""
    if not scope_value and isinstance(auth, dict):
        scope_value = auth.get("scope") or ""
    scopes = {scope for scope in scope_value.split() if scope}
    if required_scope not in scopes:
        if required_scope == "mcp:read" and method in {"jwt", "workos"}:
            return
        raise PermissionError(f"Missing required scope: {required_scope}")


def _normalize_duration(value: str | None, *, fallback: str) -> str:
    token = (value or fallback).strip()
    if not DURATION_RE.match(token):
        raise ValueError("Invalid duration. Use format like 30m, 1h, 24h.")
    return token


def _sanitize_dataset(value: str | None, *, fallback: str) -> str:
    token = (value or fallback).strip()
    if not DATASET_RE.match(token):
        return fallback
    return token


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    if number in (float("inf"), float("-inf")):
        return None
    return number


def _extract_vector_values(results: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for item in results:
        value = item.get("value")
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            parsed = _safe_float(value[1])
            if parsed is not None:
                values.append(parsed)
    return values


def _extract_scalar(results: list[dict[str, Any]]) -> float | None:
    values = _extract_vector_values(results)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return sum(values)


def _extract_uptime(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "status": "unknown",
            "checks": [
                {
                    "name": "backend_up",
                    "status": "unknown",
                    "notes": "no uptime data",
                }
            ],
        }

    down_instances: list[str] = []
    total = 0
    for item in results:
        total += 1
        value = item.get("value")
        metric = item.get("metric") or {}
        name = (
            metric.get("instance")
            or metric.get("job")
            or metric.get("pod")
            or metric.get("service")
            or "unknown"
        )
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            numeric = _safe_float(value[1])
        else:
            numeric = None
        if numeric is None or numeric < 1:
            down_instances.append(str(name))

    up_count = max(total - len(down_instances), 0)
    if up_count == 0:
        status = "critical"
    elif down_instances:
        status = "warning"
    else:
        status = "ok"

    check = {
        "name": "backend_up",
        "status": status,
        "value": {
            "up": up_count,
            "down": len(down_instances),
            "total": total,
            "down_instances": down_instances,
        },
    }
    return {"status": status, "checks": [check]}


def _evaluate_threshold(value: float | None, ok: float, warn: float) -> str:
    if value is None:
        return "unknown"
    if value <= ok:
        return "ok"
    if value <= warn:
        return "warning"
    return "critical"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    token = value.strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _tabular_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables:
        return []
    table = tables[0]
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    names = [col.get("name") if isinstance(col, dict) else None for col in columns]
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        entry: dict[str, Any] = {}
        for idx, value in enumerate(row):
            key = names[idx] if idx < len(names) else None
            if not key:
                key = f"col_{idx}"
            entry[key] = value
        output.append(entry)
    return output


def _build_promql(window: str, compare_offset: str | None = None) -> dict[str, str]:
    filters = 'endpoint!~"/api/v1/(health|ready)"'
    error_filters = f'{filters},status_code=~"5.."'
    offset = f" offset {compare_offset}" if compare_offset else ""

    request_rate = f"sum(rate(instainstru_http_requests_total{{{filters}}}[{window}]{offset}))"
    error_rate = (
        f"sum(rate(instainstru_http_requests_total{{{error_filters}}}[{window}]{offset}))"
        f" / sum(rate(instainstru_http_requests_total{{{filters}}}[{window}]{offset}))"
    )
    p99 = (
        "histogram_quantile(0.99, sum by (le)(rate("
        f"instainstru_http_request_duration_seconds_bucket{{{filters}}}[{window}]{offset}"
        ")) )"
    )
    return {"request_rate": request_rate, "error_rate": error_rate, "p99": p99}


def _build_axiom_apl(dataset: str, window: str) -> dict[str, str]:
    ingestion = (
        f"['{dataset}']\n"
        f"| where ['_time'] >= ago({window})\n"
        "| summarize spans = count(), traces = dcount(trace_id), "
        "error_spans = countif(error == true) by ['service.name']\n"
        "| sort by spans desc"
    )
    root_slo = (
        f"['{dataset}']\n"
        f"| where ['_time'] >= ago({window})\n"
        "| where isnull(parent_span_id)\n"
        "| summarize requests = count(), errors = countif(error == true), "
        "p50 = percentile(duration, 50), p95 = percentile(duration, 95), "
        "p99 = percentile(duration, 99) by ['service.name']"
    )
    slow_ops = (
        f"['{dataset}']\n"
        f"| where ['_time'] >= ago({window})\n"
        "| where isnull(parent_span_id)\n"
        "| summarize requests = count(), p99 = percentile(duration, 99) "
        "by ['service.name'], name\n"
        "| sort by p99 desc\n"
        "| limit 10"
    )
    return {"ingestion": ingestion, "root_slo": root_slo, "slow_ops": slow_ops}


def _build_action(
    title: str,
    status: str,
    reason: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "priority": 0 if status == "critical" else 1,
        "status": status,
        "title": title,
        "reason": reason,
        "tool": {"name": tool_name, "arguments": arguments or {}},
    }


def _build_top_actions(
    *,
    latency_status: str,
    latency_value: float | None,
    error_status: str,
    error_value: float | None,
    alerts_count: int,
    celery_queue_status: str,
    celery_failures_status: str,
    payment_health_status: str,
    pipeline_status: str,
    payouts_status: str,
    window: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    if latency_status in {"warning", "critical"}:
        reason = (
            f"p99 latency {latency_value:.0f}ms"
            if latency_value is not None
            else "p99 latency high"
        )
        actions.append(
            _build_action(
                "Investigate latency spike",
                latency_status,
                reason,
                "instainstru_metrics_query",
                {"question": "p99 latency", "time_window": window},
            )
        )

    if error_status in {"warning", "critical"}:
        percent = error_value * 100 if error_value is not None else None
        reason = f"error rate {percent:.2f}%" if percent is not None else "error rate elevated"
        actions.append(
            _build_action(
                "Inspect elevated error rate",
                error_status,
                reason,
                "instainstru_metrics_query",
                {"question": "error rate", "time_window": window},
            )
        )

    if alerts_count > 0:
        actions.append(
            _build_action(
                "Review firing alerts",
                "warning",
                f"{alerts_count} Grafana alerts firing",
                "instainstru_alerts_list",
                {"state": "firing"},
            )
        )

    if celery_queue_status in {"warning", "critical"}:
        actions.append(
            _build_action(
                "Check Celery queue depth",
                celery_queue_status,
                "Queue depth above threshold",
                "instainstru_celery_queue_depth",
                {},
            )
        )

    if celery_failures_status in {"warning", "critical"}:
        actions.append(
            _build_action(
                "Investigate failed Celery tasks",
                celery_failures_status,
                "Recent task failures detected",
                "instainstru_celery_failed_tasks",
                {"limit": 20},
            )
        )

    if payment_health_status in {"warning", "critical"}:
        actions.append(
            _build_action(
                "Review payment health",
                payment_health_status,
                "Payment pipeline reported issues",
                "instainstru_celery_payment_health",
                {},
            )
        )

    if pipeline_status in {"warning", "critical"}:
        actions.append(
            _build_action(
                "Audit payments pipeline",
                pipeline_status,
                "Overdue authorizations/captures",
                "instainstru_payments_pipeline",
                {},
            )
        )

    if payouts_status in {"warning", "critical"}:
        actions.append(
            _build_action(
                "Follow up on pending payouts",
                payouts_status,
                "Old payouts awaiting transfer",
                "instainstru_payments_pending_payouts",
                {"limit": 20},
            )
        )

    return actions[:5]


def register_tools(
    mcp: FastMCP,
    client: InstaInstruClient,
    grafana: GrafanaCloudClient,
    sentry: SentryClient,
    axiom: AxiomClient | None = None,
) -> dict[str, object]:
    axiom_client = axiom or AxiomClient()

    async def safe_fetch(
        source_name: str, fetch_fn: Callable[[], Awaitable[Any]]
    ) -> dict[str, Any]:
        """Wrap fetch with error handling - never fail the whole snapshot."""
        try:
            result = await fetch_fn()
            return {"status": "ok", "data": result, "source": source_name}
        except Exception as exc:
            return {
                "status": "unknown",
                "data": None,
                "source": source_name,
                "error": str(exc),
            }

    async def _fetch_sentry_top(env_value: str, limit: int = 10) -> dict[str, Any]:
        environment = env_value if env_value in {"production", "preview"} else "production"
        query = sentry_tools._build_issue_query("unresolved", None)
        issues = await sentry.list_issues(
            project="-1",
            environment=environment,
            stats_period="1h",
            status="unresolved",
            sort="user",
            limit=limit,
            query=query,
        )
        formatted = [sentry_tools._format_issue(issue) for issue in issues]
        total_events = sum(sentry_tools._safe_int(issue.get("count")) for issue in issues)
        users_affected = sum(sentry_tools._safe_int(issue.get("userCount")) for issue in issues)
        return {
            "summary": {
                "issues_returned": len(formatted),
                "total_events": total_events,
                "users_affected": users_affected,
                "time_range": "1h",
                "environment": environment,
                "note": "Totals are across returned issues only, not all issues in org",
            },
            "issues": formatted,
        }

    async def instainstru_command_center_snapshot(
        env: str = "production",
        window: str = DEFAULT_WINDOW,
        compare_offset: str = DEFAULT_COMPARE_OFFSET,
        include_growth: bool = True,
    ) -> dict:
        """
        Get a comprehensive snapshot of production health.

        Returns status for:
        - Stability: uptime, latency, errors, Celery, Sentry, tracing
        - Money: payment health, pipeline, pending payouts
        - Growth: bookings, search analytics

        Each section includes current values, 24h comparison, and thresholds.
        """
        _require_scope("mcp:read")

        now = datetime.now(timezone.utc)
        env_value = (env or "production").strip().lower()
        window_value = _normalize_duration(window, fallback=DEFAULT_WINDOW)
        compare_value = _normalize_duration(compare_offset, fallback=DEFAULT_COMPARE_OFFSET)
        dataset = _sanitize_dataset(
            os.getenv("AXIOM_LOGS_DATASET"),
            fallback="instainstru-logs",
        )

        promql_now = _build_promql(window_value)
        promql_prev = _build_promql(window_value, compare_value)
        apl_queries = _build_axiom_apl(dataset, window_value)

        tasks: list[Awaitable[dict[str, Any]]] = [
            safe_fetch(
                "prometheus.uptime",
                lambda: grafana.query_prometheus('up{job="backend"}'),
            ),
            safe_fetch(
                "prometheus.rps",
                lambda: grafana.query_prometheus(promql_now["request_rate"]),
            ),
            safe_fetch(
                "prometheus.rps_prev",
                lambda: grafana.query_prometheus(promql_prev["request_rate"]),
            ),
            safe_fetch(
                "prometheus.p99",
                lambda: grafana.query_prometheus(promql_now["p99"]),
            ),
            safe_fetch(
                "prometheus.p99_prev",
                lambda: grafana.query_prometheus(promql_prev["p99"]),
            ),
            safe_fetch(
                "prometheus.error_rate",
                lambda: grafana.query_prometheus(promql_now["error_rate"]),
            ),
            safe_fetch(
                "prometheus.error_rate_prev",
                lambda: grafana.query_prometheus(promql_prev["error_rate"]),
            ),
            safe_fetch("grafana.alerts", lambda: grafana.list_alerts(state="firing")),
            safe_fetch("celery.workers", client.get_celery_workers),
            safe_fetch("celery.queues", client.get_celery_queues),
            safe_fetch(
                "celery.failed_tasks",
                lambda: client.get_celery_failed_tasks(limit=20),
            ),
            safe_fetch("money.payment_health", client.get_celery_payment_health),
            safe_fetch("money.payments_pipeline", client.get_payment_pipeline),
            safe_fetch(
                "money.pending_payouts",
                lambda: client.get_pending_payouts(limit=20),
            ),
            safe_fetch(
                "sentry.issues_top",
                lambda: _fetch_sentry_top(env_value, limit=10),
            ),
            safe_fetch(
                "axiom.ingestion",
                lambda: axiom_client.query_apl(apl_queries["ingestion"]),
            ),
            safe_fetch(
                "axiom.root_slo",
                lambda: axiom_client.query_apl(apl_queries["root_slo"]),
            ),
            safe_fetch(
                "axiom.slow_ops",
                lambda: axiom_client.query_apl(apl_queries["slow_ops"]),
            ),
        ]

        if include_growth:
            tasks.extend(
                [
                    safe_fetch(
                        "growth.bookings_today",
                        lambda: client.get_booking_summary(period="today"),
                    ),
                    safe_fetch(
                        "growth.bookings_yesterday",
                        lambda: client.get_booking_summary(period="yesterday"),
                    ),
                    safe_fetch(
                        "growth.bookings_last_7_days",
                        lambda: client.get_booking_summary(period="last_7_days"),
                    ),
                    safe_fetch(
                        "growth.search_top_queries",
                        lambda: client.get_top_queries(limit=50),
                    ),
                    safe_fetch(
                        "growth.search_zero_results",
                        lambda: client.get_zero_results(limit=50),
                    ),
                ]
            )

        results = await asyncio.gather(*tasks)
        results_map = {item["source"]: item for item in results}

        errors = [
            {
                "source": item["source"],
                "error": item.get("error"),
            }
            for item in results
            if item.get("status") != "ok"
        ]

        def _get_data(key: str) -> dict[str, Any] | None:
            payload = results_map.get(key)
            if not payload or payload.get("status") != "ok":
                return None
            return payload.get("data")

        uptime_payload = _get_data("prometheus.uptime")
        uptime_results = uptime_payload.get("results", []) if uptime_payload else []
        uptime_section = _extract_uptime(uptime_results)

        rps_now_payload = _get_data("prometheus.rps")
        rps_prev_payload = _get_data("prometheus.rps_prev")
        rps_now = _extract_scalar(rps_now_payload.get("results", [])) if rps_now_payload else None
        rps_prev = (
            _extract_scalar(rps_prev_payload.get("results", [])) if rps_prev_payload else None
        )
        traffic_status = "unknown" if rps_now is None else ("warning" if rps_now <= 0 else "ok")
        traffic_checks = [
            {
                "name": "request_rate",
                "status": traffic_status,
                "value": rps_now,
                "unit": "rps",
                "comparison": calculate_delta(rps_now, rps_prev),
            }
        ]

        p99_now_payload = _get_data("prometheus.p99")
        p99_prev_payload = _get_data("prometheus.p99_prev")
        p99_now_sec = (
            _extract_scalar(p99_now_payload.get("results", [])) if p99_now_payload else None
        )
        p99_prev_sec = (
            _extract_scalar(p99_prev_payload.get("results", [])) if p99_prev_payload else None
        )
        p99_now = p99_now_sec * 1000 if p99_now_sec is not None else None
        p99_prev = p99_prev_sec * 1000 if p99_prev_sec is not None else None
        latency_status = _evaluate_threshold(
            p99_now, THRESHOLDS["latency_p99_ok"], THRESHOLDS["latency_p99_warn"]
        )
        latency_checks = [
            {
                "name": "p99_latency",
                "status": latency_status,
                "value": p99_now,
                "unit": "ms",
                "thresholds": {
                    "ok": THRESHOLDS["latency_p99_ok"],
                    "warning": THRESHOLDS["latency_p99_warn"],
                },
                "comparison": calculate_delta(p99_now, p99_prev),
            }
        ]

        error_now_payload = _get_data("prometheus.error_rate")
        error_prev_payload = _get_data("prometheus.error_rate_prev")
        error_now = (
            _extract_scalar(error_now_payload.get("results", [])) if error_now_payload else None
        )
        error_prev = (
            _extract_scalar(error_prev_payload.get("results", [])) if error_prev_payload else None
        )
        error_status = _evaluate_threshold(
            error_now, THRESHOLDS["error_rate_ok"], THRESHOLDS["error_rate_warn"]
        )
        error_checks = [
            {
                "name": "error_rate",
                "status": error_status,
                "value": error_now,
                "unit": "ratio",
                "thresholds": {
                    "ok": THRESHOLDS["error_rate_ok"],
                    "warning": THRESHOLDS["error_rate_warn"],
                },
                "comparison": calculate_delta(error_now, error_prev),
            }
        ]

        alerts_payload_raw = _get_data("grafana.alerts")
        if isinstance(alerts_payload_raw, list):
            alerts_payload: list[dict[str, Any]] = [
                item for item in alerts_payload_raw if isinstance(item, dict)
            ]
        else:
            alerts_payload = []
        firing_alerts = [alert for alert in alerts_payload if alert.get("state") == "firing"]
        alerts_count = len(firing_alerts)
        alerts_status = "warning" if firing_alerts else "ok"
        alerts_section = {
            "status": alerts_status,
            "firing_count": alerts_count,
            "firing": firing_alerts,
        }

        workers_payload = _get_data("celery.workers") or {}
        workers_summary = workers_payload.get("summary", {})
        offline_workers = workers_summary.get("offline_workers") or 0
        total_workers = workers_summary.get("total_workers") or 0
        if total_workers == 0:
            worker_status = "unknown"
        elif offline_workers == total_workers:
            worker_status = "critical"
        elif offline_workers > 0:
            worker_status = "warning"
        else:
            worker_status = "ok"
        workers_section = {
            "status": worker_status,
            "summary": workers_summary,
            "workers": workers_payload.get("workers", []),
        }

        queues_payload = _get_data("celery.queues") or {}
        total_depth = queues_payload.get("total_depth")
        if isinstance(total_depth, (int, float)):
            queue_status = _evaluate_threshold(
                float(total_depth),
                THRESHOLDS["celery_queue_warn"],
                THRESHOLDS["celery_queue_critical"],
            )
        else:
            queue_status = "unknown"
        queues_section = {
            "status": queue_status,
            "total_depth": total_depth,
            "queues": queues_payload.get("queues", []),
            "thresholds": {
                "warning": THRESHOLDS["celery_queue_warn"],
                "critical": THRESHOLDS["celery_queue_critical"],
            },
        }

        failures_payload = _get_data("celery.failed_tasks") or {}
        failure_count = failures_payload.get("count")
        if isinstance(failure_count, (int, float)):
            failures_status = _evaluate_threshold(
                float(failure_count),
                THRESHOLDS["celery_failures_warn"],
                THRESHOLDS["celery_failures_critical"],
            )
        else:
            failures_status = "unknown"
        failures_section = {
            "status": failures_status,
            "count": failure_count,
            "failed_tasks": failures_payload.get("failed_tasks", []),
            "thresholds": {
                "warning": THRESHOLDS["celery_failures_warn"],
                "critical": THRESHOLDS["celery_failures_critical"],
            },
        }

        celery_status = calculate_status(
            [
                {"status": worker_status},
                {"status": queue_status},
                {"status": failures_status},
            ]
        )

        sentry_payload = _get_data("sentry.issues_top") or {}
        sentry_issues = sentry_payload.get("issues", [])
        sentry_status = "warning" if sentry_issues else "ok"
        sentry_section = {
            "status": sentry_status,
            "headline": sentry_payload.get("summary"),
            "top_issues": sentry_issues,
        }

        ingestion_rows = _tabular_rows(_get_data("axiom.ingestion") or {})
        root_rows = _tabular_rows(_get_data("axiom.root_slo") or {})
        slow_rows = _tabular_rows(_get_data("axiom.slow_ops") or {})
        tracing_status = "ok" if ingestion_rows or root_rows else "unknown"
        tracing_section = {
            "status": tracing_status,
            "ingestion": ingestion_rows,
            "root_spans": root_rows,
            "top_slowest_operations": slow_rows,
        }

        stability_checks = [
            {"status": uptime_section["status"]},
            {"status": traffic_status},
            {"status": latency_status},
            {"status": error_status},
            {"status": alerts_status},
            {"status": celery_status},
            {"status": sentry_status},
            {"status": tracing_status},
        ]
        stability_status = calculate_status(stability_checks)

        payment_health_payload = _get_data("money.payment_health") or {}
        payment_health_issues = payment_health_payload.get("issues", [])
        payment_health_status = "ok"
        for issue in payment_health_issues:
            severity = (issue.get("severity") or "").lower()
            if severity == "critical":
                payment_health_status = "critical"
                break
            if severity == "warning":
                payment_health_status = "warning"
        if (
            payment_health_payload
            and payment_health_payload.get("healthy") is False
            and payment_health_status == "ok"
        ):
            payment_health_status = "warning"
        if not payment_health_payload:
            payment_health_status = "unknown"

        payments_pipeline_payload = _get_data("money.payments_pipeline") or {}
        overdue_authorizations = payments_pipeline_payload.get("overdue_authorizations")
        overdue_captures = payments_pipeline_payload.get("overdue_captures")
        pipeline_status = "ok"
        if isinstance(overdue_authorizations, int) and overdue_authorizations > 0:
            pipeline_status = "warning"
        if isinstance(overdue_captures, int) and overdue_captures > 0:
            pipeline_status = "warning"
        if not payments_pipeline_payload:
            pipeline_status = "unknown"

        pending_payouts_payload = _get_data("money.pending_payouts") or {}
        payouts = pending_payouts_payload.get("payouts", [])
        oldest_hours: float | None = None
        for payout in payouts:
            oldest = _parse_datetime(payout.get("oldest_pending_date"))
            if not oldest:
                continue
            hours = (now - oldest).total_seconds() / 3600
            if oldest_hours is None or hours > oldest_hours:
                oldest_hours = hours
        if oldest_hours is None:
            payouts_status = "ok" if payouts == [] else "unknown"
        elif oldest_hours >= THRESHOLDS["payout_age_critical_hours"]:
            payouts_status = "critical"
        elif oldest_hours >= THRESHOLDS["payout_age_warn_hours"]:
            payouts_status = "warning"
        else:
            payouts_status = "ok"

        money_status = calculate_status(
            [
                {"status": payment_health_status},
                {"status": pipeline_status},
                {"status": payouts_status},
            ]
        )

        growth_status = "ok"
        growth_section: dict[str, Any]
        if include_growth:
            bookings_today = _get_data("growth.bookings_today") or {}
            bookings_yesterday = _get_data("growth.bookings_yesterday") or {}
            bookings_last_7 = _get_data("growth.bookings_last_7_days") or {}
            today_summary = (bookings_today.get("summary") or {}) if bookings_today else {}
            yesterday_summary = (
                (bookings_yesterday.get("summary") or {}) if bookings_yesterday else {}
            )
            today_total = today_summary.get("total_bookings")
            yesterday_total = yesterday_summary.get("total_bookings")
            delta_bookings = (
                calculate_delta(float(today_total), float(yesterday_total))
                if isinstance(today_total, (int, float))
                and isinstance(yesterday_total, (int, float))
                else calculate_delta(None, None)
            )

            growth_section = {
                "status": growth_status,
                "bookings": {
                    "today": bookings_today,
                    "yesterday": bookings_yesterday,
                    "last_7_days": bookings_last_7,
                    "delta_today_vs_yesterday": delta_bookings,
                },
                "search": {
                    "top_queries": _get_data("growth.search_top_queries") or {},
                    "zero_results": _get_data("growth.search_zero_results") or {},
                },
            }
        else:
            growth_status = "unknown"
            growth_section = {
                "status": "skipped",
                "reason": "include_growth=false",
            }

        overall_status, overall_severity = calculate_overall(
            stability_status, money_status, growth_status
        )

        summary: list[str] = []
        if latency_status in {"warning", "critical"}:
            summary.append(
                f"Latency p99 {p99_now:.0f}ms ({latency_status})"
                if p99_now is not None
                else "Latency p99 unknown"
            )
        if error_status in {"warning", "critical"}:
            summary.append(
                f"Error rate {error_now:.2%} ({error_status})"
                if error_now is not None
                else "Error rate unknown"
            )
        if alerts_count:
            summary.append(f"{alerts_count} alerts firing")
        if payment_health_status in {"warning", "critical"}:
            summary.append("Payment health issues detected")
        if payouts_status in {"warning", "critical"}:
            summary.append("Pending payouts aging")
        if not summary:
            summary.append("All monitored systems healthy")

        top_actions = _build_top_actions(
            latency_status=latency_status,
            latency_value=p99_now,
            error_status=error_status,
            error_value=error_now,
            alerts_count=alerts_count,
            celery_queue_status=queue_status,
            celery_failures_status=failures_status,
            payment_health_status=payment_health_status,
            pipeline_status=pipeline_status,
            payouts_status=payouts_status,
            window=window_value,
        )

        return {
            "meta": {
                "schema_version": SCHEMA_VERSION,
                "generated_at": now.isoformat(),
                "env": env_value,
                "window": window_value,
                "compare_offset": compare_value,
            },
            "overall": {
                "status": overall_status,
                "severity": overall_severity,
                "summary": summary,
                "top_actions": top_actions,
            },
            "stability": {
                "status": stability_status,
                "checks": {
                    "uptime": uptime_section,
                    "traffic": {"status": traffic_status, "checks": traffic_checks},
                    "latency": {"status": latency_status, "checks": latency_checks},
                    "errors": {"status": error_status, "checks": error_checks},
                },
                "alerts": alerts_section,
                "celery": {
                    "status": celery_status,
                    "workers": workers_section,
                    "queues": queues_section,
                    "failures": failures_section,
                },
                "sentry": sentry_section,
                "tracing": tracing_section,
            },
            "money": {
                "status": money_status,
                "payment_health": {
                    "status": payment_health_status,
                    "details": payment_health_payload,
                },
                "payments_pipeline": {
                    "status": pipeline_status,
                    "details": payments_pipeline_payload,
                },
                "pending_payouts": {
                    "status": payouts_status,
                    "oldest_pending_age_hours": oldest_hours,
                    "details": pending_payouts_payload,
                },
            },
            "growth": growth_section,
            "debug": {
                "sources_used": [
                    {"source": item["source"], "status": item.get("status")} for item in results
                ],
                "errors": errors,
            },
        }

    mcp.tool()(instainstru_command_center_snapshot)

    return {"instainstru_command_center_snapshot": instainstru_command_center_snapshot}
