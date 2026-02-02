# Axiom Monitors for InstaInstru

## Overview
- Dataset: instainstru-logs
- Signals: error spikes (OTel status), p99 latency, ingestion volume
- Notifications: Slack or email

## Setup (Axiom UI)
1. Open Axiom and select the instainstru-logs dataset.
2. Go to Monitors or Alerts (label varies by UI) and create a new monitor.
3. Paste the APL query, set the evaluation window, and configure a threshold.
4. Add Slack/email notification destinations (monitors without notifiers will not alert).
5. Axiom does not have a built-in severity selector; encode severity in the monitor name and/or route to different notifiers.

## Monitor 1: Error Spike (OTel status)
APL query (current dataset fields use `status.code` as a string): 

```apl
['instainstru-logs']
| where _time > ago(5m)
| where ['status.code'] == "ERROR"
| summarize error_count = count() by ['service.name']
```

Threshold:
- Trigger when error_count > 5 in a 5 minute window
- Use Notify by group to alert per service

Note:
- `instainstru-logs` does not currently expose HTTP status codes. If you need strict 5xx monitoring, add an HTTP status attribute to spans/logs (e.g., `attributes.http.response.status_code`) and update this query to use it.

Quick field check (handy when schema changes):

```apl
['instainstru-logs']
| summarize count() by ['status.code']
```

## Monitor 2: P99 Latency Threshold
APL query (duration stored in nanoseconds; convert to ms):

```apl
['instainstru-logs']
| where _time > ago(5m)
| extend duration_ms = duration / 1000000
| summarize p99_duration_ms = percentile(duration_ms, 99) by ['service.name']
```

Optional: restrict to HTTP spans only (if you want request latency):

```apl
['instainstru-logs']
| where _time > ago(5m)
| where isnotempty(['attributes.http.route'])
| extend duration_ms = duration / 1000000
| summarize p99_duration_ms = percentile(duration_ms, 99) by ['service.name']
```

Threshold:
- Trigger when any service p99_duration_ms > 500 for 5 minutes
- Use Notify by group to alert per service

Note:
- If you see values like 5.0e+07 in results, those are nanoseconds. Keep the ms conversion and use a 500 ms threshold.

## Monitor 3: Ingestion Drop
APL query:

```apl
['instainstru-logs']
| where _time > ago(15m)
| count
```

Threshold:
- Trigger when count < 10 in 15 minutes (expected ~6000)
- Alert on no data enabled

## Recommended Check Options (Quick Reference)
| Monitor | Trigger | Check every | Lookback | Alert on no data | Notify by group |
| --- | --- | --- | --- | --- | --- |
| Error spike | Above 5 | 5 min | 5 min | Off | On |
| P99 latency (warning) | Above 500 ms | 5 min | 5 min | Off | On |
| Ingestion drop | Below 10 | 5 min | 15 min | On | Off |

If limited to 3 monitors, prioritize the three above. Add a sustained critical p99 monitor later (e.g., lookback 15–30 min) when you have more monitor slots.

## Runbook (Quick Response)
- Error spike: Check Sentry issues, recent deploys, and API error logs.
- p99 latency: Review slow endpoints, DB performance, and queue depth.
- Ingestion drop: Verify OTEL_EXPORTER_OTLP_* env vars and service uptime.
