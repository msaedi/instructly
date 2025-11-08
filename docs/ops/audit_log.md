# Audit Log Operations

## Overview

The audit log tracks key lifecycle events for bookings and availability so that administrators can review who changed what and when. The following actions are recorded:

- Booking create, update, cancel, complete events
- Availability week saves and week copy operations

Each entry captures:

- Entity type (`booking` or `availability`) and identifier
- Action name
- Actor id and role (student, instructor, admin, or system)
- Timestamp (`occurred_at`)
- Redacted `before` and `after` payloads showing relevant state snapshots

## Redaction Policy

Audit payloads are shallowly sanitized before persistence. Sensitive keys are masked (`[REDACTED]`) so that emails, contact details, payment metadata, and free-form notes do not leak into the log. The helper is lightweight and easy to extend – update `app/services/audit_redaction.py` if new fields need to be hidden.

## Querying the Log

`GET /api/admin/audit` (admin role required) exposes a filterable, paginated view.

Supported query parameters:

- `entity_type`, `entity_id`
- `action`
- `actor_id`, `actor_role`
- `start`, `end` – ISO8601 timestamps (inclusive range)
- `limit` (default 50, maximum 200), `offset`

Results are ordered by `occurred_at DESC`. The endpoint is intentionally uncached so the latest writes are always visible.

### Example

```bash
curl \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  'https://api.example.com/api/admin/audit?entity_type=booking&entity_id=bk_123&limit=25'
```

Sample response excerpt:

```json
{
  "items": [
    {
      "id": "01HC5MAB62E5...",
      "entity_type": "booking",
      "entity_id": "bk_123",
      "action": "cancel",
      "actor_id": "student_42",
      "actor_role": "student",
      "occurred_at": "2025-01-05T17:42:11.082Z",
      "before": {"status": "CONFIRMED", "student_note": "[REDACTED]"},
      "after": {"status": "CANCELLED", "student_note": "[REDACTED]"}
    }
  ],
  "total": 3,
  "limit": 25,
  "offset": 0
}
```

## Access Control

- Only admins can call the endpoint (`requires_roles("admin")`). Non-admin requests receive `403`.
- Responses are never cached; every request hits the database to surface the most recent events.

## Observability

Prometheus records the following derived metrics (rule file `infra/observability/prometheus/rules/audit.yml`):

- `audit:write_rate_5m`, `audit:write_rate_5m_by_entity`, `audit:write_rate_5m_by_entity_action` – 5-minute rate of audit writes, aggregated at different dimensionalities.
- `audit:read_rate_5m` – 5-minute rate of admin audit fetches.
- `audit:list_latency_avg_5m`, `audit:list_latency_p50_5m`, `audit:list_latency_p95_5m`, `audit:list_latency_p99_5m` – rolling average and latency quantiles built from the histogram exported by the API.

A provisioned Grafana dashboard called **Audit Overview** (see `infra/observability/grafana/dashboards/audit.json`) visualizes these metrics, including write/read overview stats, latency percentiles, action mix heatmap, top actors, and drill-down tables. The dashboard lives in the *Instainstru* folder once Grafana reloads provisioning.

### Operational SLO

- Target: `audit:list_latency_p95_5m < 0.3s` (p95 list latency under 300 ms based on the recording rule). Investigate if the panel breaches for more than two consecutive intervals.

### Alerts

- `AuditListLatencyP95High` (warning): fires if `audit:list_latency_p95_5m` stays above 300 ms for 10 minutes. Confirm the Grafana Audit Overview latency panels, inspect recent deploys, and review Postgres slow query logs for `audit_log_entries`. If sustained, consider enabling query plan logging and verifying the `entity`/`action` fan-out volumes.
- `AuditListLatencyP95VeryHigh` (critical): p95 latency above 600 ms for 10 minutes. Page the on-call engineer, check database saturation (CPU, IOPS) and Redis cache hit rate, and roll back the most recent release if a regression is suspected.
