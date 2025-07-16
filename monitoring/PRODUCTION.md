# Production Monitoring Deployment Guide

This guide covers deploying InstaInstru's monitoring infrastructure to production using Grafana Cloud, the recommended approach for production environments.

## Table of Contents
- [Why Grafana Cloud](#why-grafana-cloud)
- [Setup Guide](#setup-guide)
- [Exporting from Local Grafana](#exporting-from-local-grafana)
- [Environment Variables](#environment-variables)
- [Security Best Practices](#security-best-practices)
- [SLIs and SLOs](#slis-and-slos)
- [Backup Procedures](#backup-procedures)
- [Cost Estimation](#cost-estimation)
- [Terraform Deployment](#terraform-deployment)

## Why Grafana Cloud

Grafana Cloud provides a managed monitoring solution that includes:
- **Managed Prometheus**: No need to run your own Prometheus server
- **Managed Grafana**: Always up-to-date, highly available
- **Integrated Alerting**: Built-in alertmanager with multi-channel support
- **Global Distribution**: Edge locations for better performance
- **Automatic Backups**: Dashboard and alert configuration backups
- **SSO Integration**: Enterprise authentication options
- **SLA Guarantee**: 99.5% uptime SLA

## Setup Guide

### 1. Create Grafana Cloud Account

1. Visit [grafana.com/products/cloud](https://grafana.com/products/cloud/)
2. Sign up for a free account (includes 10k metrics)
3. Choose your cloud region (select closest to your users)
4. Note your organization slug and API endpoints

### 2. Configure Prometheus Remote Write

Your backend application needs to send metrics to Grafana Cloud:

```python
# In your FastAPI app configuration
GRAFANA_CLOUD_METRICS_URL = os.getenv("GRAFANA_CLOUD_METRICS_URL")
GRAFANA_CLOUD_METRICS_USER = os.getenv("GRAFANA_CLOUD_METRICS_USER")
GRAFANA_CLOUD_API_KEY = os.getenv("GRAFANA_CLOUD_API_KEY")

# Configure Prometheus remote write
from prometheus_client import CollectorRegistry, push_to_gateway
import prometheus_client.openmetrics.exposition as openmetrics

# Push metrics to Grafana Cloud
def push_metrics():
    gateway_url = f"{GRAFANA_CLOUD_METRICS_URL}/api/prom/push"
    auth_handler = lambda: (GRAFANA_CLOUD_METRICS_USER, GRAFANA_CLOUD_API_KEY)
    push_to_gateway(
        gateway_url,
        job='instainstru-backend',
        registry=registry,
        handler=auth_handler
    )
```

### 3. Configure Your Application

Add Grafana Cloud remote write to your existing metrics endpoint:

```python
# backend/app/metrics/prometheus_metrics.py
import os
from urllib.parse import urlparse

class GrafanaCloudExporter:
    def __init__(self):
        self.enabled = bool(os.getenv("GRAFANA_CLOUD_METRICS_URL"))
        if self.enabled:
            self.url = os.getenv("GRAFANA_CLOUD_METRICS_URL")
            self.user = os.getenv("GRAFANA_CLOUD_METRICS_USER")
            self.api_key = os.getenv("GRAFANA_CLOUD_API_KEY")

    def export_metrics(self, registry):
        if not self.enabled:
            return

        # Export metrics to Grafana Cloud
        # Implementation depends on your metrics library
```

## Exporting from Local Grafana

### Export Dashboards

1. In your local Grafana (http://localhost:3003):
   - Go to each dashboard
   - Click the share icon → Export → Save to file
   - Save as JSON

2. For bulk export:
```bash
# Export all dashboards
for dashboard in $(curl -s -u admin:${GRAFANA_PASSWORD} \
  http://localhost:3003/api/search | jq -r '.[].uid'); do
  curl -s -u admin:${GRAFANA_PASSWORD} \
    "http://localhost:3003/api/dashboards/uid/${dashboard}" \
    > "monitoring/exports/dashboard-${dashboard}.json"
done
```

### Export Alert Rules

```bash
# Export alert rules
curl -s -u admin:${GRAFANA_PASSWORD} \
  http://localhost:3003/api/v1/provisioning/alert-rules \
  > monitoring/exports/alert-rules.json

# Export contact points
curl -s -u admin:${GRAFANA_PASSWORD} \
  http://localhost:3003/api/v1/provisioning/contact-points \
  > monitoring/exports/contact-points.json
```

## Environment Variables

### Production Environment Variables

Create a `.env.production` file (DO NOT COMMIT):

```bash
# Grafana Cloud Configuration
GRAFANA_CLOUD_API_KEY=glc_xxxxxxxxxxxx
GRAFANA_CLOUD_METRICS_URL=https://prometheus-us-central1.grafana.net
GRAFANA_CLOUD_METRICS_USER=123456
GRAFANA_CLOUD_LOGS_URL=https://logs-prod-us-central1.grafana.net
GRAFANA_CLOUD_LOGS_USER=123456
GRAFANA_CLOUD_TRACES_URL=https://tempo-us-central1.grafana.net:443

# Application Metrics
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
METRICS_ENABLED=true
METRICS_INCLUDE_IN_SCHEMA=false

# Alert Channels
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
PAGERDUTY_INTEGRATION_KEY=your-pagerduty-key
ALERT_EMAIL_ADDRESSES=oncall@company.com,engineering@company.com

# Security
GRAFANA_CLOUD_STACK_SLUG=yourcompany
GRAFANA_CLOUD_REGION=us
```

### Kubernetes ConfigMap Example

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: monitoring-config
data:
  GRAFANA_CLOUD_METRICS_URL: "https://prometheus-us-central1.grafana.net"
  GRAFANA_CLOUD_LOGS_URL: "https://logs-prod-us-central1.grafana.net"
  METRICS_ENABLED: "true"
  PROMETHEUS_MULTIPROC_DIR: "/tmp/prometheus"
```

## Security Best Practices

### 1. API Key Management

- Use separate API keys for different environments
- Rotate API keys every 90 days
- Store keys in secure secret management (AWS Secrets Manager, Vault)
- Never commit API keys to version control

### 2. Network Security

```yaml
# Kubernetes NetworkPolicy example
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: grafana-cloud-egress
spec:
  podSelector:
    matchLabels:
      app: instainstru-backend
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 443
  - to:  # Allow DNS
    - namespaceSelector: {}
    ports:
    - protocol: UDP
      port: 53
```

### 3. Authentication & Authorization

- Enable SSO with your identity provider (Google, Okta, etc.)
- Use Grafana Cloud's built-in RBAC
- Create teams with appropriate permissions:
  - **Viewers**: Read-only access to dashboards
  - **Editors**: Can modify dashboards and alerts
  - **Admins**: Full access including billing

### 4. Data Retention & Privacy

- Configure appropriate data retention (default: 30 days)
- Enable audit logging for compliance
- Use label filters to exclude sensitive data:

```yaml
metric_relabel_configs:
  - source_labels: [__name__]
    regex: '.*password.*|.*secret.*|.*token.*'
    action: drop
```

## SLIs and SLOs

### Service Level Indicators (SLIs)

1. **Response Time (Latency)**
   - SLI: 99th percentile of response times
   - Target: < 500ms for 99% of requests
   - Query: `histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))`

2. **Availability**
   - SLI: Ratio of successful requests to total requests
   - Target: 99.9% availability
   - Query: `sum(rate(http_requests_total{status!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))`

3. **Error Rate**
   - SLI: Percentage of 5xx responses
   - Target: < 1% error rate
   - Query: `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100`

4. **Cache Performance**
   - SLI: Cache hit ratio
   - Target: > 80% hit rate
   - Query: `sum(rate(cache_hits_total[5m])) / (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m]))) * 100`

### Service Level Objectives (SLOs)

Configure SLO monitoring in Grafana Cloud:

```json
{
  "name": "API Availability SLO",
  "description": "99.9% of requests should be successful",
  "sli": {
    "events": {
      "good_events_query": "sum(rate(http_requests_total{status!~\"5..\"}[5m]))",
      "total_events_query": "sum(rate(http_requests_total[5m]))"
    }
  },
  "objectives": [
    {
      "value": 0.999,
      "window": "30d",
      "name": "99.9% over 30 days"
    },
    {
      "value": 0.999,
      "window": "7d",
      "name": "99.9% over 7 days"
    }
  ],
  "alerting": {
    "burn_rate_thresholds": [
      {
        "long_window": "1h",
        "short_window": "5m",
        "burn_rate": 14.4
      }
    ]
  }
}
```

### Error Budget Tracking

Calculate and monitor error budgets:

```
Error Budget = 100% - SLO Target
Monthly Error Budget (99.9% SLO) = 43.2 minutes of downtime

Remaining Budget = (1 - (errors / total_requests)) - SLO
```

## Backup Procedures

### 1. Automated Backups

Grafana Cloud automatically backs up:
- Dashboards (every 1 hour)
- Alert rules (every 1 hour)
- Data sources (every 1 hour)

### 2. Manual Export Script

Create `monitoring/scripts/backup-grafana.sh`:

```bash
#!/bin/bash
GRAFANA_URL="https://${GRAFANA_CLOUD_STACK_SLUG}.grafana.net"
BACKUP_DIR="monitoring/backups/$(date +%Y%m%d)"

mkdir -p "$BACKUP_DIR"

# Export dashboards
curl -H "Authorization: Bearer ${GRAFANA_CLOUD_API_KEY}" \
  "${GRAFANA_URL}/api/search?type=dash-db" | \
  jq -r '.[].uid' | while read uid; do
    curl -H "Authorization: Bearer ${GRAFANA_CLOUD_API_KEY}" \
      "${GRAFANA_URL}/api/dashboards/uid/${uid}" \
      > "${BACKUP_DIR}/dashboard-${uid}.json"
done

# Export alerts
curl -H "Authorization: Bearer ${GRAFANA_CLOUD_API_KEY}" \
  "${GRAFANA_URL}/api/v1/provisioning/alert-rules" \
  > "${BACKUP_DIR}/alert-rules.json"

# Compress backup
tar -czf "${BACKUP_DIR}.tar.gz" "${BACKUP_DIR}"
rm -rf "${BACKUP_DIR}"

# Upload to S3 (optional)
aws s3 cp "${BACKUP_DIR}.tar.gz" s3://your-backup-bucket/grafana/
```

### 3. Disaster Recovery

Recovery procedure:
1. Create new Grafana Cloud stack
2. Run Terraform to provision infrastructure
3. Import dashboards and alerts from backup
4. Update application configuration with new endpoints
5. Verify metrics flow and alerting

## Cost Estimation

### Grafana Cloud Free Tier
- 10,000 active series
- 50 GB logs
- 50 GB traces
- 3 users
- **Cost: $0/month**

### Grafana Cloud Pro (Recommended for Production)
- 15,000 active series included
- 100 GB logs included
- 100 GB traces included
- Unlimited users
- **Base Cost: $299/month**

### Additional Costs
- Extra metrics: $8 per 1,000 series/month
- Extra logs: $0.50 per GB/month
- Extra traces: $0.50 per GB/month

### Cost Optimization Tips

1. **Reduce Cardinality**
   ```python
   # Bad: High cardinality
   counter.labels(user_id=user.id, endpoint=endpoint)

   # Good: Lower cardinality
   counter.labels(endpoint=endpoint, status_code=status)
   ```

2. **Use Recording Rules**
   ```yaml
   groups:
     - name: aggregations
       interval: 30s
       rules:
         - record: job:http_requests:rate5m
           expr: sum(rate(http_requests_total[5m])) by (job)
   ```

3. **Implement Sampling**
   - Sample traces (1% for high-volume endpoints)
   - Aggregate metrics before sending
   - Use log sampling for high-volume logs

## Terraform Deployment

The `monitoring/terraform/` directory contains Infrastructure as Code for Grafana Cloud setup. See the [Terraform README](terraform/README.md) for detailed instructions.

Quick start:
```bash
cd monitoring/terraform
terraform init
terraform plan -var-file=environments/production.tfvars
terraform apply -var-file=environments/production.tfvars
```

## Migration Checklist

- [ ] Create Grafana Cloud account
- [ ] Export dashboards from local Grafana
- [ ] Export alert rules and contact points
- [ ] Set up environment variables
- [ ] Configure application for remote write
- [ ] Run Terraform to provision infrastructure
- [ ] Import dashboards to Grafana Cloud
- [ ] Configure alert notification channels
- [ ] Test metrics flow
- [ ] Verify alerts are working
- [ ] Update documentation with new endpoints
- [ ] Train team on Grafana Cloud interface

## Support and Resources

- [Grafana Cloud Documentation](https://grafana.com/docs/grafana-cloud/)
- [Prometheus Remote Write](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#remote_write)
- [Grafana Cloud Status](https://status.grafana.com/)
- Support: support@grafana.com (Pro/Advanced plans)
