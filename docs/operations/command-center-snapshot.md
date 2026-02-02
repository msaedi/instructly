# Command Center Snapshot

## Usage

Ask MCP: "Show me the command center snapshot"

Tool name: `instainstru_command_center_snapshot`

Example:

```json
{
  "env": "production",
  "window": "30m",
  "compare_offset": "24h",
  "include_growth": true
}
```

## Response Interpretation

### Overall Status
- ✅ `ok` - All systems healthy
- ⚠️ `warning` - Minor issues, monitor
- 🔴 `critical` - Immediate action needed
- ❓ `unknown` - Data missing; verify sources

### Top Actions
When issues exist, `top_actions` provides prioritized next steps with suggested drilldown tool calls.

### Stability
Includes uptime, traffic, latency, error rate, alerts, Celery, Sentry, and tracing.
Each check includes current values and a 24h comparison when available.

### Money
Includes payment health, payments pipeline, and pending payouts with aging detection.

### Growth
Includes bookings (today/yesterday/last 7 days) and search analytics.

## Thresholds

- Latency p99 OK: `<= 400ms`
- Latency p99 Warning: `<= 800ms`
- Error rate OK: `<= 0.5%`
- Error rate Warning: `<= 2%`
- Celery queue depth Warning: `>= 50`
- Celery queue depth Critical: `>= 200`
- Celery failures Warning: `>= 1`
- Celery failures Critical: `>= 5`
- Pending payouts Warning: `>= 48h` oldest pending
- Pending payouts Critical: `>= 168h` (7 days) oldest pending

## Notes

- The snapshot is designed to degrade gracefully if a data source is unavailable.
- Growth data is optional and can be disabled via `include_growth=false`.
