"""MCP tools for Grafana Cloud observability."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from ..grafana_client import (
    GrafanaAuthError,
    GrafanaCloudClient,
    GrafanaConnectionError,
    GrafanaNotConfiguredError,
    GrafanaNotFoundError,
    GrafanaRateLimitError,
    GrafanaRequestError,
)

QUESTION_ALIASES: dict[str, str] = {
    "p99 latency": "p99",
    "p99": "p99",
    "latency": "p99",
    "response time": "p99",
    "p50 latency": "p50",
    "p50": "p50",
    "median latency": "p50",
    "request rate": "request_rate",
    "rps": "request_rate",
    "traffic": "request_rate",
    "throughput": "request_rate",
    "error rate": "error_rate",
    "errors": "error_rate",
    "5xx": "error_rate",
    "5xx rate": "error_rate",
    "requests by endpoint": "requests_by_endpoint",
    "latency by endpoint": "latency_by_endpoint",
    "endpoint latency": "latency_by_endpoint",
    "slowest endpoints": "slowest_endpoints",
    "slow endpoints": "slowest_endpoints",
}


GOLDEN_QUERIES: dict[str, dict[str, Any]] = {
    "p99": {
        "description": "99th percentile latency",
        "unit": "seconds",
        "format": "latency_ms",
        "template": (
            "histogram_quantile(0.99, sum by (le) "
            "(rate(instainstru_http_request_duration_seconds_bucket{filters}[{window}])))"
        ),
    },
    "p50": {
        "description": "Median latency",
        "unit": "seconds",
        "format": "latency_ms",
        "template": (
            "histogram_quantile(0.50, sum by (le) "
            "(rate(instainstru_http_request_duration_seconds_bucket{filters}[{window}])))"
        ),
    },
    "request_rate": {
        "description": "Request rate",
        "unit": "requests/second",
        "format": "rps",
        "template": "sum(rate(instainstru_http_requests_total{filters}[{window}]))",
    },
    "error_rate": {
        "description": "Error rate (5xx / total)",
        "unit": "ratio",
        "format": "percent",
        "template": (
            "sum(rate(instainstru_http_requests_total{error_filters}[{window}])) "
            "/ sum(rate(instainstru_http_requests_total{filters}[{window}]))"
        ),
    },
    "requests_by_endpoint": {
        "description": "Request rate per endpoint",
        "unit": "requests/second",
        "format": "table",
        "template": "sum by (endpoint) (rate(instainstru_http_requests_total{filters}[{window}]))",
    },
    "latency_by_endpoint": {
        "description": "P99 latency per endpoint",
        "unit": "seconds",
        "format": "table",
        "template": (
            "histogram_quantile(0.99, sum by (le, endpoint) "
            "(rate(instainstru_http_request_duration_seconds_bucket{filters}[{window}])))"
        ),
    },
    "slowest_endpoints": {
        "description": "Top 10 slowest endpoints by P99 latency",
        "unit": "seconds",
        "format": "table",
        "template": (
            "topk(10, histogram_quantile(0.99, sum by (le, endpoint) "
            "(rate(instainstru_http_request_duration_seconds_bucket{filters}[{window}]))))"
        ),
    },
}


def register_tools(mcp: FastMCP, grafana: GrafanaCloudClient) -> dict[str, object]:
    async def instainstru_prometheus_query(query: str, time: str | None = None) -> dict:
        """Execute a PromQL instant query."""
        try:
            _require_scope("mcp:read")
            resolved_time = _resolve_time(time) if time else None
            return await grafana.query_prometheus(query=query, time=resolved_time)
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_prometheus_query_range(
        query: str,
        start: str,
        end: str | None = None,
        step: str = "60s",
    ) -> dict:
        """Execute a PromQL range query for time-series data."""
        try:
            _require_scope("mcp:read")
            resolved_start, resolved_end = _resolve_range(start, end)
            return await grafana.query_prometheus_range(
                query=query,
                start=resolved_start,
                end=resolved_end,
                step=step,
            )
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_dashboards_list() -> dict:
        """List available Grafana dashboards."""
        try:
            _require_scope("mcp:read")
            dashboards = await grafana.list_dashboards()
            return {"dashboards": dashboards, "count": len(dashboards)}
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_dashboard_panels(dashboard_uid: str) -> dict:
        """Get panel information from a dashboard."""
        try:
            _require_scope("mcp:read")
            dashboard = await grafana.get_dashboard(dashboard_uid)
            panels = _extract_panels(dashboard.get("panels", []))
            return {
                "dashboard_uid": dashboard_uid,
                "title": dashboard.get("title"),
                "panels": panels,
                "count": len(panels),
            }
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_alerts_list(state: str | None = None) -> dict:
        """List current alerts from Grafana alerting."""
        try:
            _require_scope("mcp:read")
            alerts = await grafana.list_alerts(state=state)
            return {"alerts": alerts, "count": len(alerts)}
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_alert_silence(
        matchers: list[dict[str, Any]],
        duration_minutes: int,
        comment: str,
        created_by: str = "instainstru-mcp",
    ) -> dict:
        """Create a silence for alerts matching specified labels."""
        try:
            _require_scope("mcp:write")
            return await grafana.create_silence(
                matchers=matchers,
                duration_minutes=duration_minutes,
                comment=comment,
                created_by=created_by,
            )
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_silences_list(active_only: bool = True) -> dict:
        """List alert silences."""
        try:
            _require_scope("mcp:read")
            silences = await grafana.list_silences(active_only=active_only)
            return {"silences": silences, "count": len(silences)}
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_metrics_query(
        question: str,
        time_window: str = "5m",
        exclude_health_endpoints: bool = True,
    ) -> dict:
        """Answer common observability questions using golden queries."""
        try:
            _require_scope("mcp:read")
            resolved_key = _resolve_question(question)
            query_info = GOLDEN_QUERIES.get(resolved_key)
            if not query_info:
                return {
                    "error": "unknown_question",
                    "message": "Unsupported question. Try: p99 latency, error rate, request rate.",
                    "supported_questions": sorted(QUESTION_ALIASES.keys()),
                }

            promql = _build_promql(
                resolved_key,
                time_window=time_window,
                exclude_health_endpoints=exclude_health_endpoints,
            )
            result = await grafana.query_prometheus(query=promql)
            results = result.get("results", [])
            format_style = query_info.get("format")
            if format_style == "table":
                numeric_value = None
                formatted = "table"
            else:
                numeric_value = _extract_instant_value(results)
                formatted = _format_value(numeric_value, format_style)

            response: dict[str, Any] = {
                "question": question,
                "resolved_question": resolved_key,
                "description": query_info.get("description"),
                "promql": promql,
                "time_window": time_window,
                "unit": query_info.get("unit"),
                "value": numeric_value,
                "formatted": formatted,
                "results": results,
            }
            return response
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    mcp.tool()(instainstru_prometheus_query)
    mcp.tool()(instainstru_prometheus_query_range)
    mcp.tool()(instainstru_dashboards_list)
    mcp.tool()(instainstru_dashboard_panels)
    mcp.tool()(instainstru_alerts_list)
    mcp.tool()(instainstru_alert_silence)
    mcp.tool()(instainstru_silences_list)
    mcp.tool()(instainstru_metrics_query)

    return {
        "instainstru_prometheus_query": instainstru_prometheus_query,
        "instainstru_prometheus_query_range": instainstru_prometheus_query_range,
        "instainstru_dashboards_list": instainstru_dashboards_list,
        "instainstru_dashboard_panels": instainstru_dashboard_panels,
        "instainstru_alerts_list": instainstru_alerts_list,
        "instainstru_alert_silence": instainstru_alert_silence,
        "instainstru_silences_list": instainstru_silences_list,
        "instainstru_metrics_query": instainstru_metrics_query,
    }


def _handle_error(exc: Exception) -> dict:
    if isinstance(exc, GrafanaNotConfiguredError):
        return {
            "error": "grafana_not_configured",
            "message": "Grafana Cloud URL or API key not configured.",
        }
    if isinstance(exc, GrafanaAuthError):
        return {"error": "grafana_auth_failed", "message": "Grafana API authentication failed."}
    if isinstance(exc, GrafanaRateLimitError):
        rate_limit_payload: dict[str, Any] = {
            "error": "grafana_rate_limited",
            "message": "Grafana API rate limit hit.",
        }
        if exc.retry_after is not None:
            rate_limit_payload["retry_after_seconds"] = exc.retry_after
        return rate_limit_payload
    if isinstance(exc, GrafanaNotFoundError):
        return {"error": "grafana_not_found", "message": "Grafana resource not found."}
    if isinstance(exc, GrafanaConnectionError):
        return {
            "error": "grafana_connection_failed",
            "message": str(exc),
        }
    if isinstance(exc, GrafanaRequestError):
        request_payload: dict[str, Any] = {
            "error": "grafana_request_failed",
            "message": str(exc),
        }
        if exc.status_code is not None:
            request_payload["status_code"] = exc.status_code
        return request_payload
    if isinstance(exc, PermissionError):
        return {"error": "insufficient_scope", "message": str(exc)}
    if isinstance(exc, ValueError):
        return {"error": "invalid_request", "message": str(exc)}
    return {"error": "unknown_error", "message": str(exc)}


def _normalize_question(question: str) -> str:
    return question.strip().lower()


def _resolve_question(question: str) -> str:
    key = _normalize_question(question)
    return QUESTION_ALIASES.get(key, key)


def _render_filters(filters: list[str]) -> str:
    if not filters:
        return ""
    return "{" + ",".join(filters) + "}"


def _build_promql(
    key: str,
    *,
    time_window: str,
    exclude_health_endpoints: bool,
) -> str:
    base_filter_list: list[str] = []
    if exclude_health_endpoints:
        base_filter_list.append('endpoint!~"/api/v1/(health|ready)"')
    base_filters = _render_filters(base_filter_list)
    template = GOLDEN_QUERIES.get(key, {}).get("template", "")
    if not template:
        return ""
    if key == "error_rate":
        error_filters = _render_filters(base_filter_list + ['status_code=~"5.."'])
        return template.format(
            filters=base_filters,
            error_filters=error_filters,
            window=time_window,
        )
    return template.format(filters=base_filters, window=time_window)


def _extract_instant_value(results: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for item in results:
        value = item.get("value")
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                values.append(float(value[1]))
            except (TypeError, ValueError):
                continue
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return sum(values)


def _format_value(value: float | None, formatter: str | None) -> str:
    if value is None:
        return "no data"
    if formatter == "latency_ms":
        return f"{value * 1000:.1f}ms"
    if formatter == "percent":
        return f"{value * 100:.2f}%"
    if formatter == "rps":
        return f"{value:.2f} req/s"
    return str(value)


def _extract_panels(panels: list[Any]) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        # Row panels can contain nested panels
        nested = panel.get("panels")
        if nested:
            extracted.extend(_extract_panels(nested))
            continue
        targets = panel.get("targets", [])
        queries = []
        for target in targets:
            if not isinstance(target, dict):
                continue
            expr = target.get("expr") or target.get("query") or target.get("rawQuery")
            if expr:
                queries.append(expr)
        extracted.append(
            {
                "id": panel.get("id"),
                "title": panel.get("title"),
                "type": panel.get("type"),
                "datasource": panel.get("datasource"),
                "queries": queries,
            }
        )
    return extracted


def _resolve_range(start: str, end: str | None) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    resolved_start = _resolve_relative_time(start, now)
    resolved_end = _resolve_relative_time(end, now) if end else now.isoformat()
    return resolved_start, resolved_end


def _resolve_time(value: str | None) -> str | None:
    if value is None:
        return None
    now = datetime.now(timezone.utc)
    return _resolve_relative_time(value, now)


def _resolve_relative_time(value: str, now: datetime) -> str:
    token = value.strip()
    if token.endswith("m") and token[:-1].isdigit():
        return (now - timedelta(minutes=int(token[:-1]))).isoformat()
    if token.endswith("h") and token[:-1].isdigit():
        return (now - timedelta(hours=int(token[:-1]))).isoformat()
    if token.endswith("d") and token[:-1].isdigit():
        return (now - timedelta(days=int(token[:-1]))).isoformat()
    try:
        if token.endswith("Z"):
            token = token[:-1] + "+00:00"
        parsed = datetime.fromisoformat(token)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except ValueError as exc:
        raise ValueError("Invalid time format. Use ISO 8601 or relative (e.g., 1h, 30m).") from exc


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
