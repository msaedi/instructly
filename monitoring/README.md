# InstaInstru Monitoring Stack

## Overview

This directory contains the complete monitoring infrastructure for InstaInstru, including:
- Prometheus for metrics collection
- Grafana for visualization and alerting
- Pre-configured dashboards and alerts
- Test scripts for validation

## Quick Start

1. **Configure environment variables**:
   ```bash
   cp .env.monitoring.example .env.monitoring
   # Edit .env.monitoring with your credentials and webhook URLs
   ```

2. **Start the monitoring stack**:
   ```bash
   docker-compose -f docker-compose.monitoring.yml up -d
   ```

3. **Access Grafana**:
   - URL: http://localhost:3003
   - Username: Value from GRAFANA_ADMIN_USER in .env.monitoring
   - Password: Value from GRAFANA_ADMIN_PASSWORD in .env.monitoring

## Components

### Prometheus
- Collects metrics from the FastAPI backend
- Scrapes endpoints every 15 seconds
- Stores time-series data for queries

### Grafana
- 3 pre-configured dashboards
- 5 alert rules with notification routing
- Alert status panels on dashboards
- Optional Slack notifications (configure in .env.monitoring)

### Dashboards

1. **Service Performance Dashboard**
   - Service response times
   - Operation latency heatmap
   - Anomaly detection (Z-score)
   - SLA compliance metrics
   - Alert status indicators

2. **API Health Dashboard**
   - HTTP request metrics
   - Error rates and status codes
   - Endpoint performance
   - Rate limiting metrics

3. **Business Metrics Dashboard**
   - Booking statistics
   - User activity
   - Revenue metrics
   - Growth indicators

## Alerts

Configured alerts include:
- High Response Time (P95 > 500ms)
- High Error Rate (> 1%)
- Service Degradation (P99 > 1s)
- High Request Load (> 1000 req/s)
- Low Cache Hit Rate (< 60%)

See [ALERTING.md](./ALERTING.md) for detailed configuration.

### Slack Notifications

To enable Slack notifications:
1. Add your webhook URL to `.env.monitoring`
2. Configure through Grafana UI (recommended)
3. See [SLACK_SETUP.md](./SLACK_SETUP.md) for instructions

## Testing

Run the alert test script to validate your setup:
```bash
./monitoring/test-alerts.sh
```

This will simulate conditions to trigger all configured alerts.

Test Slack notifications:
```bash
./monitoring/test-slack.sh
```

## Directory Structure

```
monitoring/
├── grafana/
│   └── provisioning/
│       ├── alerting/          # Alert rules and notification channels
│       ├── dashboards/        # Dashboard JSON files
│       └── datasources/       # Prometheus datasource config
├── prometheus/
│   └── prometheus.yml         # Prometheus configuration
├── grafana-data/             # Grafana persistent storage (created at runtime)
├── prometheus-data/          # Prometheus data (created at runtime)
├── ALERTING.md              # Alert configuration guide
├── README.md                # This file
└── test-alerts.sh          # Alert testing script
```

## Maintenance

### Updating Dashboards
1. Make changes in Grafana UI
2. Export dashboard JSON
3. Replace file in `grafana/provisioning/dashboards/`
4. Restart Grafana container

### Adding New Alerts
1. Edit `grafana/provisioning/alerting/alerting.yml`
2. Add notification routing in `notification-policies.yml`
3. Restart Grafana container

### Backup
Important data to backup:
- `.env.monitoring` (credentials)
- `grafana/provisioning/` (configurations)
- `grafana-data/` (if you have custom dashboards)

## Troubleshooting

### Grafana not starting
- Check logs: `docker-compose -f docker-compose.monitoring.yml logs grafana`
- Verify `.env.monitoring` exists and has valid values

### No metrics appearing
- Ensure backend is running: `curl http://localhost:8000/health`
- Check Prometheus targets: http://localhost:9090/targets
- Verify metrics endpoint: `curl http://localhost:8000/metrics/prometheus`

### Alerts not firing
- Check alert rules in Grafana: Alerting → Alert rules
- Test notification channels: Alerting → Contact points → Test
- Review alert conditions and thresholds

## Performance Impact

The monitoring stack has minimal impact:
- Prometheus scraping adds ~1-2ms to request latency
- Metrics collection uses ~50MB RAM
- Disk usage grows ~100MB/day (with retention policies)
