"""MCP tools for metrics definitions."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..client import InstaInstruClient

METRICS_DICTIONARY: dict[str, dict[str, Any]] = {
    # Core HTTP metrics
    "instainstru_http_request_duration_seconds": {
        "name": "instainstru_http_request_duration_seconds",
        "type": "histogram",
        "description": "HTTP request latency in seconds",
        "labels": ["method", "endpoint", "status_code"],
        "use_for": ["p50 latency", "p90 latency", "p99 latency", "latency distribution"],
        "default_window": "5m",
        "golden_query_p99": (
            "histogram_quantile(0.99, "
            "sum by (le) (rate(instainstru_http_request_duration_seconds_bucket"
            '{endpoint!~"/api/v1/(health|ready)"}[5m])))'
        ),
        "golden_query_p50": (
            "histogram_quantile(0.50, "
            "sum by (le) (rate(instainstru_http_request_duration_seconds_bucket"
            '{endpoint!~"/api/v1/(health|ready)"}[5m])))'
        ),
        "unit": "seconds",
        "exclude_from_slo": ["/api/v1/health", "/api/v1/ready"],
    },
    "instainstru_http_requests_total": {
        "name": "instainstru_http_requests_total",
        "type": "counter",
        "description": "Total HTTP requests",
        "labels": ["method", "endpoint", "status_code"],
        "use_for": ["request rate", "traffic volume", "error rate"],
        "default_window": "5m",
        "golden_query_rps": "sum(rate(instainstru_http_requests_total[5m]))",
        "golden_query_error_rate": (
            'sum(rate(instainstru_http_requests_total{status_code=~"5.."}[5m])) '
            "/ sum(rate(instainstru_http_requests_total[5m]))"
        ),
        "unit": "requests",
    },
    "instainstru_http_requests_in_progress": {
        "name": "instainstru_http_requests_in_progress",
        "type": "gauge",
        "description": "In-flight HTTP requests",
        "labels": ["method", "endpoint"],
        "use_for": ["concurrency", "load"],
        "unit": "requests",
    },
    "instainstru_service_operation_duration_seconds": {
        "name": "instainstru_service_operation_duration_seconds",
        "type": "histogram",
        "description": "Service operation duration in seconds",
        "labels": ["service", "operation"],
        "use_for": ["service latency", "slow operations"],
        "unit": "seconds",
    },
    "instainstru_service_operations_total": {
        "name": "instainstru_service_operations_total",
        "type": "counter",
        "description": "Service operations by status",
        "labels": ["service", "operation", "status"],
        "use_for": ["success/error rates"],
        "unit": "operations",
    },
    "instainstru_errors_total": {
        "name": "instainstru_errors_total",
        "type": "counter",
        "description": "Errors by service/operation/error_type",
        "labels": ["service", "operation", "error_type"],
        "use_for": ["error counts", "error hotspots"],
        "unit": "errors",
    },
    # Cache + domain counters
    "instainstru_profile_pic_url_cache_hits_total": {
        "name": "instainstru_profile_pic_url_cache_hits_total",
        "type": "counter",
        "description": "Profile picture URL cache hits",
        "labels": ["variant"],
        "use_for": ["cache hit rate"],
        "unit": "hits",
    },
    "instainstru_profile_pic_url_cache_misses_total": {
        "name": "instainstru_profile_pic_url_cache_misses_total",
        "type": "counter",
        "description": "Profile picture URL cache misses",
        "labels": ["variant"],
        "use_for": ["cache miss rate"],
        "unit": "misses",
    },
    "instainstru_credits_applied_total": {
        "name": "instainstru_credits_applied_total",
        "type": "counter",
        "description": "Credits applied (authorization/cancellation/etc.)",
        "labels": ["source"],
        "use_for": ["credit usage"],
        "unit": "credits",
    },
    "instainstru_instant_payout_requests_total": {
        "name": "instainstru_instant_payout_requests_total",
        "type": "counter",
        "description": "Instant payout requests by status",
        "labels": ["status"],
        "use_for": ["payout health"],
        "unit": "requests",
    },
    "instainstru_beta_phase_header_total": {
        "name": "instainstru_beta_phase_header_total",
        "type": "counter",
        "description": "Responses by x-beta-phase header",
        "labels": ["phase"],
        "use_for": ["beta phase distribution"],
        "unit": "responses",
    },
    "instainstru_preview_bypass_total": {
        "name": "instainstru_preview_bypass_total",
        "type": "counter",
        "description": "Preview bypass events by mechanism",
        "labels": ["via"],
        "use_for": ["preview security auditing"],
        "unit": "events",
    },
    "instainstru_notifications_outbox_total": {
        "name": "instainstru_notifications_outbox_total",
        "type": "counter",
        "description": "Notification outbox events by status",
        "labels": ["status", "event_type"],
        "use_for": ["notification success rate"],
        "unit": "events",
    },
    "instainstru_notifications_outbox_attempt_total": {
        "name": "instainstru_notifications_outbox_attempt_total",
        "type": "counter",
        "description": "Notification outbox delivery attempts",
        "labels": ["event_type"],
        "use_for": ["delivery retries"],
        "unit": "attempts",
    },
    "instainstru_availability_events_suppressed_total": {
        "name": "instainstru_availability_events_suppressed_total",
        "type": "counter",
        "description": "Availability events suppressed before dispatch",
        "labels": ["reason"],
        "use_for": ["availability pipeline health"],
        "unit": "events",
    },
    "instainstru_booking_lock_operations_total": {
        "name": "instainstru_booking_lock_operations_total",
        "type": "counter",
        "description": "Booking lock operations by action/outcome",
        "labels": ["action", "outcome"],
        "use_for": ["locking health"],
        "unit": "operations",
    },
    "instainstru_notifications_dispatch_seconds": {
        "name": "instainstru_notifications_dispatch_seconds",
        "type": "histogram",
        "description": "Notification dispatch duration in seconds",
        "labels": ["event_type"],
        "use_for": ["notification latency"],
        "unit": "seconds",
    },
    "instainstru_audit_log_write_total": {
        "name": "instainstru_audit_log_write_total",
        "type": "counter",
        "description": "Audit log writes by entity/action",
        "labels": ["entity_type", "action"],
        "use_for": ["audit volume"],
        "unit": "writes",
    },
    "instainstru_audit_log_read_total": {
        "name": "instainstru_audit_log_read_total",
        "type": "counter",
        "description": "Audit log list invocations",
        "labels": [],
        "use_for": ["audit reads"],
        "unit": "reads",
    },
    "instainstru_audit_log_list_seconds": {
        "name": "instainstru_audit_log_list_seconds",
        "type": "histogram",
        "description": "Audit log listing duration in seconds",
        "labels": [],
        "use_for": ["audit latency"],
        "unit": "seconds",
    },
    "instainstru_prometheus_scrapes_total": {
        "name": "instainstru_prometheus_scrapes_total",
        "type": "counter",
        "description": "Prometheus scrape count",
        "labels": [],
        "use_for": ["scrape volume"],
        "unit": "scrapes",
    },
    # Rate limit metrics
    "instainstru_rl_decisions_total": {
        "name": "instainstru_rl_decisions_total",
        "type": "counter",
        "description": "Rate-limit decisions",
        "labels": ["bucket", "action", "shadow"],
        "use_for": ["rate-limit enforcement"],
        "unit": "decisions",
    },
    "instainstru_rl_retry_after_seconds": {
        "name": "instainstru_rl_retry_after_seconds",
        "type": "histogram",
        "description": "Retry-after values in seconds",
        "labels": ["bucket", "shadow"],
        "use_for": ["rate-limit delays"],
        "unit": "seconds",
    },
    "instainstru_rl_eval_errors_total": {
        "name": "instainstru_rl_eval_errors_total",
        "type": "counter",
        "description": "Rate-limit evaluation errors",
        "labels": ["bucket"],
        "use_for": ["rate-limit errors"],
        "unit": "errors",
    },
    "instainstru_rl_eval_duration_seconds": {
        "name": "instainstru_rl_eval_duration_seconds",
        "type": "histogram",
        "description": "Rate-limit evaluation duration in seconds",
        "labels": ["bucket"],
        "use_for": ["rate-limit latency"],
        "unit": "seconds",
    },
    "instainstru_rl_config_reload_total": {
        "name": "instainstru_rl_config_reload_total",
        "type": "counter",
        "description": "Rate-limit config reloads",
        "labels": [],
        "use_for": ["config reloads"],
        "unit": "reloads",
    },
    "instainstru_rl_active_overrides": {
        "name": "instainstru_rl_active_overrides",
        "type": "gauge",
        "description": "Active rate-limit overrides",
        "labels": [],
        "use_for": ["override count"],
        "unit": "overrides",
    },
    # Search metrics
    "instainstru_nl_search_latency_ms": {
        "name": "instainstru_nl_search_latency_ms",
        "type": "histogram",
        "description": "NL search latency by stage (milliseconds)",
        "labels": ["stage", "cache_hit", "parsing_mode"],
        "use_for": ["search latency"],
        "unit": "milliseconds",
    },
    "instainstru_nl_search_openai_latency_ms": {
        "name": "instainstru_nl_search_openai_latency_ms",
        "type": "histogram",
        "description": "OpenAI API latency (milliseconds)",
        "labels": ["endpoint"],
        "use_for": ["LLM latency"],
        "unit": "milliseconds",
    },
    "instainstru_nl_search_result_count": {
        "name": "instainstru_nl_search_result_count",
        "type": "histogram",
        "description": "Search result count distribution",
        "labels": [],
        "use_for": ["result quality"],
        "unit": "results",
    },
    "instainstru_nl_search_zero_results_total": {
        "name": "instainstru_nl_search_zero_results_total",
        "type": "counter",
        "description": "Searches returning zero results",
        "labels": ["has_constraints"],
        "use_for": ["zero-result rate"],
        "unit": "searches",
    },
    "instainstru_nl_search_typo_corrections_total": {
        "name": "instainstru_nl_search_typo_corrections_total",
        "type": "counter",
        "description": "Typo corrections made",
        "labels": ["confidence"],
        "use_for": ["typo correction volume"],
        "unit": "corrections",
    },
    "instainstru_nl_search_query_complexity": {
        "name": "instainstru_nl_search_query_complexity",
        "type": "histogram",
        "description": "Search query constraint count",
        "labels": ["parsing_mode"],
        "use_for": ["query complexity"],
        "unit": "constraints",
    },
    "instainstru_nl_search_cache_hit_total": {
        "name": "instainstru_nl_search_cache_hit_total",
        "type": "counter",
        "description": "Search cache hits",
        "labels": ["cache_type"],
        "use_for": ["cache hit rate"],
        "unit": "hits",
    },
    "instainstru_nl_search_cache_miss_total": {
        "name": "instainstru_nl_search_cache_miss_total",
        "type": "counter",
        "description": "Search cache misses",
        "labels": ["cache_type"],
        "use_for": ["cache miss rate"],
        "unit": "misses",
    },
    "instainstru_nl_search_circuit_breaker_state": {
        "name": "instainstru_nl_search_circuit_breaker_state",
        "type": "gauge",
        "description": "Circuit breaker state (0=closed,1=half-open,2=open)",
        "labels": ["component"],
        "use_for": ["degradation monitoring"],
        "unit": "state",
    },
    "instainstru_nl_search_degradation_total": {
        "name": "instainstru_nl_search_degradation_total",
        "type": "counter",
        "description": "Search degradation events",
        "labels": ["level", "component"],
        "use_for": ["degradation volume"],
        "unit": "events",
    },
    "instainstru_nl_search_requests_total": {
        "name": "instainstru_nl_search_requests_total",
        "type": "counter",
        "description": "Search requests by status",
        "labels": ["status"],
        "use_for": ["search volume"],
        "unit": "requests",
    },
    # Login protection metrics
    "instainstru_login_attempts_total": {
        "name": "instainstru_login_attempts_total",
        "type": "counter",
        "description": "Login attempts by result",
        "labels": ["result"],
        "use_for": ["auth health"],
        "unit": "attempts",
    },
    "instainstru_login_rate_limited_total": {
        "name": "instainstru_login_rate_limited_total",
        "type": "counter",
        "description": "Rate-limited login attempts by reason",
        "labels": ["reason"],
        "use_for": ["rate limiting"],
        "unit": "attempts",
    },
    "instainstru_login_lockouts_total": {
        "name": "instainstru_login_lockouts_total",
        "type": "counter",
        "description": "Login lockouts by threshold",
        "labels": ["threshold"],
        "use_for": ["lockout monitoring"],
        "unit": "lockouts",
    },
    "instainstru_login_captcha_required_total": {
        "name": "instainstru_login_captcha_required_total",
        "type": "counter",
        "description": "Captcha challenges during login",
        "labels": ["result"],
        "use_for": ["captcha monitoring"],
        "unit": "challenges",
    },
    "instainstru_login_slot_wait_seconds": {
        "name": "instainstru_login_slot_wait_seconds",
        "type": "histogram",
        "description": "Wait time for login concurrency slot",
        "labels": [],
        "use_for": ["login throttling latency"],
        "unit": "seconds",
    },
    # Background-check + job metrics (non-instainstru prefix but exposed)
    "bgc_invites_total": {
        "name": "bgc_invites_total",
        "type": "counter",
        "description": "Background-check invites by outcome",
        "labels": ["outcome"],
        "use_for": ["BGC invite volume"],
        "unit": "invites",
    },
    "checkr_webhook_total": {
        "name": "checkr_webhook_total",
        "type": "counter",
        "description": "Checkr webhook events processed",
        "labels": ["result", "outcome"],
        "use_for": ["BGC webhook volume"],
        "unit": "events",
    },
    "background_job_failures_total": {
        "name": "background_job_failures_total",
        "type": "counter",
        "description": "Background jobs failed",
        "labels": ["type"],
        "use_for": ["job failures"],
        "unit": "failures",
    },
    "background_jobs_failed": {
        "name": "background_jobs_failed",
        "type": "gauge",
        "description": "Jobs in dead-letter queue",
        "labels": [],
        "use_for": ["job backlog"],
        "unit": "jobs",
    },
    "instainstru_metrics_auth_fail_total": {
        "name": "instainstru_metrics_auth_fail_total",
        "type": "counter",
        "description": "Protected metrics endpoint auth failures",
        "labels": ["reason"],
        "use_for": ["metrics auth"],
        "unit": "failures",
    },
    "bgc_final_adverse_scheduled_total": {
        "name": "bgc_final_adverse_scheduled_total",
        "type": "counter",
        "description": "Final adverse action jobs scheduled",
        "labels": [],
        "use_for": ["BGC adverse actions"],
        "unit": "jobs",
    },
    "bgc_final_adverse_executed_total": {
        "name": "bgc_final_adverse_executed_total",
        "type": "counter",
        "description": "Final adverse action job outcomes",
        "labels": ["outcome"],
        "use_for": ["BGC adverse actions"],
        "unit": "jobs",
    },
    "bgc_report_id_encrypt_total": {
        "name": "bgc_report_id_encrypt_total",
        "type": "counter",
        "description": "BGC report identifiers encrypted",
        "labels": ["source"],
        "use_for": ["BGC encryption"],
        "unit": "events",
    },
    "bgc_report_id_decrypt_total": {
        "name": "bgc_report_id_decrypt_total",
        "type": "counter",
        "description": "BGC report identifiers decrypted",
        "labels": [],
        "use_for": ["BGC decryption"],
        "unit": "events",
    },
    "bgc_pending_over_7d": {
        "name": "bgc_pending_over_7d",
        "type": "gauge",
        "description": "Instructors pending background check >7 days",
        "labels": [],
        "use_for": ["BGC backlog"],
        "unit": "instructors",
    },
    # Retention purge metrics (optional Prometheus integration)
    "retention_purge_total": {
        "name": "retention_purge_total",
        "type": "counter",
        "description": "Retention purge rows deleted",
        "labels": ["table"],
        "use_for": ["data retention volume"],
        "unit": "rows",
    },
    "retention_purge_errors_total": {
        "name": "retention_purge_errors_total",
        "type": "counter",
        "description": "Retention purge errors",
        "labels": ["table"],
        "use_for": ["retention errors"],
        "unit": "errors",
    },
    "retention_purge_chunk_seconds": {
        "name": "retention_purge_chunk_seconds",
        "type": "histogram",
        "description": "Retention purge chunk duration in seconds",
        "labels": ["table"],
        "use_for": ["retention latency"],
        "unit": "seconds",
    },
}

METRIC_ALIASES: dict[str, str] = {
    "latency": "instainstru_http_request_duration_seconds",
    "p99": "instainstru_http_request_duration_seconds",
    "p99 latency": "instainstru_http_request_duration_seconds",
    "p50": "instainstru_http_request_duration_seconds",
    "p50 latency": "instainstru_http_request_duration_seconds",
    "response time": "instainstru_http_request_duration_seconds",
    "request rate": "instainstru_http_requests_total",
    "rps": "instainstru_http_requests_total",
    "traffic": "instainstru_http_requests_total",
    "throughput": "instainstru_http_requests_total",
    "errors": "instainstru_http_requests_total",
    "error rate": "instainstru_http_requests_total",
    "5xx": "instainstru_http_requests_total",
    "login attempts": "instainstru_login_attempts_total",
    "rate limits": "instainstru_rl_decisions_total",
    "search latency": "instainstru_nl_search_latency_ms",
    "search requests": "instainstru_nl_search_requests_total",
}

SUPPORTED_QUESTIONS = sorted(
    {
        "p99 latency",
        "p50 latency",
        "request rate",
        "error rate",
        "requests by endpoint",
        "latency by endpoint",
        "slowest endpoints",
    }
)


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _resolve_metric_name(metric_name: str) -> str:
    key = _normalize_key(metric_name)
    return METRIC_ALIASES.get(key, metric_name)


def _metric_aliases_for(metric_name: str) -> list[str]:
    return sorted(alias for alias, target in METRIC_ALIASES.items() if target == metric_name)


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_metrics_describe(metric_name: str | None = None) -> dict:
        """Get a metrics dictionary definition."""
        if metric_name is None or not metric_name.strip():
            metrics_list = [
                {
                    "name": definition.get("name"),
                    "type": definition.get("type"),
                    "description": definition.get("description"),
                    "labels": definition.get("labels", []),
                    "unit": definition.get("unit"),
                }
                for definition in METRICS_DICTIONARY.values()
            ]
            return {
                "metrics": metrics_list,
                "count": len(metrics_list),
                "aliases": METRIC_ALIASES,
                "supported_questions": SUPPORTED_QUESTIONS,
            }

        resolved = _resolve_metric_name(metric_name)
        definition = METRICS_DICTIONARY.get(resolved)
        if definition:
            return {
                "metric": definition,
                "resolved_name": resolved,
                "aliases": _metric_aliases_for(resolved),
            }
        return await client.get_metric(metric_name)

    mcp.tool()(instainstru_metrics_describe)

    return {"instainstru_metrics_describe": instainstru_metrics_describe}
