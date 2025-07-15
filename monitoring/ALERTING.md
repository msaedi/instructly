# InstaInstru Alerting Configuration

## Overview

This document describes how to configure and manage alerting for the InstaInstru monitoring stack.

## Alert Rules

The following alert rules are configured:

### 1. High Response Time (P95 > 500ms)
- **Severity**: Warning
- **Threshold**: P95 latency exceeds 500ms for 5 minutes
- **Team**: Backend
- **Action**: Check service performance, scale if needed

### 2. High Error Rate (> 1%)
- **Severity**: Critical
- **Threshold**: Error rate exceeds 1% for 5 minutes
- **Team**: Backend
- **Action**: Immediate investigation required

### 3. Service Degradation (P99 > 1s)
- **Severity**: Critical
- **Threshold**: P99 latency exceeds 1 second for 3 minutes
- **Team**: Backend
- **Action**: Service-specific investigation

### 4. High Request Load (> 1000 req/s)
- **Severity**: Warning
- **Threshold**: Request rate exceeds 1000 req/s for 10 minutes
- **Team**: Infrastructure
- **Action**: Monitor resources, prepare to scale

### 5. Low Cache Hit Rate (< 60%)
- **Severity**: Warning
- **Threshold**: Cache hit rate falls below 60% for 10 minutes
- **Team**: Backend
- **Action**: Investigate cache misses, check DragonflyDB

## Notification Channels

### Slack Configuration

1. Create a Slack webhook:
   - Go to https://api.slack.com/apps
   - Create a new app or use existing
   - Add "Incoming Webhooks" feature
   - Create webhook for your alert channel

2. Add webhook URL to `.env.monitoring`:
   ```bash
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

### Email Configuration

Add email addresses to `.env.monitoring`:
```bash
ALERT_EMAIL_ADDRESSES=oncall@instainstru.com,engineering@instainstru.com
```

### PagerDuty Configuration

1. Get integration key from PagerDuty service
2. Add to `.env.monitoring`:
   ```bash
   PAGERDUTY_INTEGRATION_KEY=YOUR_INTEGRATION_KEY
   ```

## Alert Routing

- **Critical alerts**: PagerDuty + Slack (immediate notification)
- **Warning alerts**: Slack only (grouped notifications)
- **Infrastructure alerts**: Email + Slack

## Testing Alerts

### Manual Alert Testing

1. Access Grafana at http://localhost:3003
2. Navigate to Alerting → Alert rules
3. Click on any rule and select "Test rule"

### Simulating Alert Conditions

Use the test script to simulate alert conditions:

```bash
./monitoring/test-alerts.sh
```

This script will:
- Generate high latency requests
- Create error responses
- Simulate cache misses
- Generate high load

## Alert Dashboards

Alert status panels are included in:
- Service Performance Dashboard (bottom row)
- API Health Dashboard (alert summary)
- Business Metrics Dashboard (SLA violations)

## Troubleshooting

### Alerts not firing

1. Check Prometheus targets:
   ```
   http://localhost:9090/targets
   ```

2. Verify alert rules are loaded:
   ```
   http://localhost:3003/alerting/list
   ```

3. Check notification channel test:
   - Grafana → Alerting → Contact points
   - Click "Test" on each contact point

### Missing metrics

1. Ensure backend is running with metrics endpoint
2. Check Prometheus scrape configuration
3. Verify metrics are being collected:
   ```
   curl http://localhost:8000/metrics/prometheus
   ```

## Best Practices

1. **Alert Fatigue**: Only alert on actionable items
2. **Clear Descriptions**: Include context and runbook links
3. **Appropriate Severity**: Reserve critical for user-impacting issues
4. **Test Regularly**: Run alert tests monthly
5. **Review Thresholds**: Adjust based on actual performance

## Runbook Links

Each alert includes a runbook link. Create runbooks at:
- https://wiki.instainstru.com/runbooks/high-response-time
- https://wiki.instainstru.com/runbooks/high-error-rate
- https://wiki.instainstru.com/runbooks/service-degradation
- https://wiki.instainstru.com/runbooks/high-load
- https://wiki.instainstru.com/runbooks/low-cache-hit-rate
