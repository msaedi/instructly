# Metrics to Grafana Cloud (Prometheus remote_write agent)

This service scrapes our API’s `/internal/metrics` endpoint and forwards samples to Grafana Cloud via remote_write. We run a lightweight Prometheus agent per environment (preview and beta/prod) to keep deployments isolated.

## Environment variables (Render)
- `BACKEND_TARGET`            : `api.preview.instainstru.com:80` or `api.instainstru.com:80`
- `CLUSTER_LABEL`             : `instainstru-preview` or `instainstru-beta`
- `PROM_REMOTE_WRITE_URL`     : `https://prometheus-prod-XX.grafana.net/api/prom/push`
- `PROM_REMOTE_WRITE_USERNAME`: Grafana Cloud instance ID (username from onboarding screen)
- `PROM_REMOTE_WRITE_PASSWORD`: Grafana Cloud API token (glc_…)
- `PROM_REMOTE_WRITE_BEARER`  : (optional) bearer token if Grafana switches authentication flows
- `METRICS_BASIC_AUTH_USER`   : Username protecting the backend `/internal/metrics` endpoint
- `METRICS_BASIC_AUTH_PASS`   : Password protecting the backend `/internal/metrics` endpoint

## Deploy (Render)
1. Create a **Web Service** (Docker) and point the Dockerfile to `monitoring/prod-agent/Dockerfile`.
2. Set the environment variables above; do **not** expose the service publicly or mount volumes.
3. For preview, use `BACKEND_TARGET=api.preview.instainstru.com:80` and `CLUSTER_LABEL=instainstru-preview`. For beta/prod, set `BACKEND_TARGET=api.instainstru.com:80` and `CLUSTER_LABEL=instainstru-beta`.
4. After deploy, verify ingestion from Grafana Cloud → Explore (Prometheus datasource) with:

```
up{cluster="instainstru-preview"}
up{cluster="instainstru-beta"}
```

Each environment should report `up == 1` within a minute.

## Alerting (Grafana Cloud)
Define Grafana Cloud alert rules (or cloud-managed Grafana Alerting) using the BGC metrics:
- `sum(rate(checkr_webhook_total{outcome="error"}[5m])) > 0`
- `increase(background_job_failures_total[5m]) > 0`
- `bgc_pending_over_7d > 0`

Before enabling production alerts, create a temporary `vector(1)` rule and route it to Slack to confirm delivery, then remove the test rule.

## Admin utilities
- Legacy `/metrics/*` utility endpoints (health, cache, rate limits, etc.) now live under `/ops/*` and require admin access in preview/beta/prod.
- Prometheus exposition remains at `/internal/metrics` (Basic Auth + optional IP allowlist).

## Local smoke (optional)
```
# build locally (optional)
docker build -t prom-agent:local -f monitoring/prod-agent/Dockerfile monitoring/prod-agent

# run with env (optional)
docker run --rm -e BACKEND_TARGET=localhost:8000 \
  -e CLUSTER_LABEL=instainstru-local \
  -e PROM_REMOTE_WRITE_URL="https://prometheus-prod-XX.grafana.net/api/prom/push" \
  -e PROM_REMOTE_WRITE_USERNAME="2722045" \
  -e PROM_REMOTE_WRITE_PASSWORD="glc_..." \
  prom-agent:local
```
