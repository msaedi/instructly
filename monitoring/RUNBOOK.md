# InstaInstru Monitoring Runbook

This runbook provides procedures for responding to monitoring alerts and investigating issues using the InstaInstru monitoring stack.

## Table of Contents
- [Common Issues and Solutions](#common-issues-and-solutions)
- [Alert Response Procedures](#alert-response-procedures)
- [Investigating High Latency](#investigating-high-latency)
- [Finding Slow Operations](#finding-slow-operations)
- [Dashboard Investigation Guide](#dashboard-investigation-guide)
- [Useful PromQL Queries](#useful-promql-queries)
- [Troubleshooting Monitoring](#troubleshooting-monitoring)

## Common Issues and Solutions

### Issue: Metrics Not Appearing in Prometheus

**Symptoms:**
- Prometheus targets show as "DOWN"
- No data in Grafana dashboards
- Empty response from `/metrics/prometheus`

**Solutions:**
1. Verify backend is running:
   ```bash
   curl http://localhost:8000/health
   ```

2. Check Prometheus targets:
   - Navigate to http://localhost:9090/targets
   - Verify "instainstru-backend" is UP

3. Check metrics endpoint directly:
   ```bash
   curl http://localhost:8000/metrics/prometheus | grep instainstru_
   ```

4. Restart services:
   ```bash
   docker-compose restart
   cd backend && uvicorn app.main:app --reload
   ```

### Issue: Alerts Not Firing

**Symptoms:**
- Known issues but no alerts in Grafana
- Alerts stuck in "pending" state

**Solutions:**
1. Check alert evaluation:
   ```
   Grafana UI → Alerting → Alert rules
   Look for "Health" column - should show "OK" or "Alerting"
   ```

2. Verify alert queries return data:
   ```promql
   # In Prometheus, test the alert query:
   (sum(rate(instainstru_http_requests_total{status_code=~"5.."}[5m])) / sum(rate(instainstru_http_requests_total[5m]))) * 100
   ```

3. Check alert configuration:
   - Ensure "for" duration has passed
   - Verify notification policies are configured

### Issue: Slack Notifications Not Working

**Symptoms:**
- Alerts fire but no Slack messages
- "Sending alerts to local notifier" in logs

**Solutions:**
1. Test Slack webhook:
   ```bash
   ./monitoring/test-slack.sh
   ```

2. Check notification routing:
   ```bash
   ./monitoring/configure-slack-routing.sh
   ```

3. Verify in Grafana UI:
   - Alerting → Contact points → Test slack-notifications
   - Alerting → Notification policies → Check routing

## Alert Response Procedures

### 🔴 High Error Rate (> 1%)

**Severity:** Critical
**Target Response Time:** 5 minutes

**Investigation Steps:**
1. Check error distribution:
   ```promql
   sum by (status_code, endpoint) (rate(instainstru_http_requests_total{status_code=~"4..|5.."}[5m]))
   ```

2. Identify error types:
   ```promql
   topk(10, sum by (endpoint, status_code) (rate(instainstru_http_requests_total{status_code=~"5.."}[5m])))
   ```

3. Check application logs:
   ```bash
   docker logs backend_app --tail 100 | grep ERROR
   ```

4. Common causes:
   - Database connection issues → Check DB connection pool
   - External service timeout → Check third-party integrations
   - Code deployment issues → Check recent deployments

**Remediation:**
- For 503 errors: Scale up instances or check resource limits
- For 500 errors: Roll back recent deployment
- For 502/504: Check upstream services and timeouts

### 🔴 Service Degradation (503 Errors)

**Severity:** Critical
**Target Response Time:** Immediate

**Investigation Steps:**
1. Check service health:
   ```promql
   sum(rate(instainstru_http_requests_total{status_code="503"}[1m])) by (endpoint)
   ```

2. Verify resource usage:
   ```promql
   # CPU usage
   rate(process_cpu_seconds_total[5m])

   # Memory usage
   process_resident_memory_bytes
   ```

3. Check database connections:
   ```promql
   instainstru_db_pool_connections_used / instainstru_db_pool_connections_max * 100
   ```

**Remediation:**
- Restart unhealthy services
- Scale horizontally if under load
- Check and increase connection pool limits
- Enable circuit breakers

### ⚠️ High Response Time (P95 > 500ms)

**Severity:** Warning
**Target Response Time:** 15 minutes

**Investigation Steps:**
1. Identify slow endpoints:
   ```promql
   topk(10, histogram_quantile(0.95, sum by (endpoint, le) (rate(instainstru_http_request_duration_seconds_bucket[5m]))))
   ```

2. Check service operation latency:
   ```promql
   topk(10, histogram_quantile(0.95, sum by (service, operation, le) (rate(instainstru_service_operation_duration_seconds_bucket[5m]))))
   ```

3. Database query performance:
   ```promql
   avg by (query_type, table) (rate(instainstru_db_query_duration_seconds_sum[5m]) / rate(instainstru_db_query_duration_seconds_count[5m]))
   ```

**Remediation:**
- Add caching for slow queries
- Optimize database queries (add indexes)
- Enable query result caching
- Consider async processing for heavy operations

### ⚠️ High Request Load (> 1000 req/s)

**Severity:** Warning
**Target Response Time:** 10 minutes

**Investigation Steps:**
1. Check request distribution:
   ```promql
   sum by (endpoint) (rate(instainstru_http_requests_total[1m]))
   ```

2. Identify traffic patterns:
   ```promql
   # Requests by method
   sum by (method) (rate(instainstru_http_requests_total[1m]))
   ```

3. Check for abuse:
   - Look for unusual user agents
   - Check single IP making many requests
   - Verify expected traffic patterns

**Remediation:**
- Enable rate limiting
- Scale up instances
- Enable CDN/caching for static content
- Block abusive IPs if necessary

### ⚠️ Low Cache Hit Rate (< 70%)

**Severity:** Warning
**Target Response Time:** 30 minutes

**Investigation Steps:**
1. Check cache performance by cache name:
   ```promql
   sum by (cache_name) (rate(instainstru_cache_hits_total[5m])) /
   (sum by (cache_name) (rate(instainstru_cache_hits_total[5m])) +
    sum by (cache_name) (rate(instainstru_cache_misses_total[5m]))) * 100
   ```

2. Check cache evictions:
   ```promql
   sum by (cache_name, reason) (rate(instainstru_cache_evictions_total[5m]))
   ```

**Remediation:**
- Increase cache size if evictions are high
- Review cache TTL settings
- Preheat cache for common queries
- Fix cache key generation if needed

## Investigating High Latency

### Step 1: Identify Slow Endpoints

```promql
# Top 10 slowest endpoints (P95)
topk(10,
  histogram_quantile(0.95,
    sum by (endpoint, le) (
      rate(instainstru_http_request_duration_seconds_bucket[5m])
    )
  )
)
```

### Step 2: Drill Down to Service Operations

```promql
# Find slow service operations for a specific endpoint
histogram_quantile(0.95,
  sum by (service, operation, le) (
    rate(instainstru_service_operation_duration_seconds_bucket{service=~".*Availability.*"}[5m])
  )
)
```

### Step 3: Check Database Queries

```promql
# Slow queries by type
topk(10,
  avg by (query_type, table) (
    rate(instainstru_db_query_duration_seconds_sum[5m]) /
    rate(instainstru_db_query_duration_seconds_count[5m])
  )
)
```

### Step 4: Analyze Call Patterns

1. In Grafana, go to "Service Performance" dashboard
2. Look for:
   - Sudden spikes in operation duration
   - Correlation with increased load
   - Specific services showing degradation

## Finding Slow Operations

### Using Grafana Dashboards

1. **API Overview Dashboard**
   - Check "Response Time (P95)" panel
   - Click on high points to zoom in
   - Note the time range

2. **Service Performance Dashboard**
   - Look at "Service Operation Duration by Method"
   - Sort by highest P95 latency
   - Click through to logs for that time period

### Using Prometheus Queries

```promql
# Operations taking > 1 second (P99)
histogram_quantile(0.99,
  sum by (service, operation, le) (
    rate(instainstru_service_operation_duration_seconds_bucket[5m])
  )
) > 1

# Service methods with highest error rates
topk(10,
  sum by (service, operation, error_type) (
    rate(instainstru_service_operation_errors_total[5m])
  )
)
```

### Correlation Analysis

```promql
# Compare request rate vs response time
# High correlation might indicate scaling issues
(
  sum(rate(instainstru_http_requests_total[5m]))
  *
  histogram_quantile(0.95, sum(rate(instainstru_http_request_duration_seconds_bucket[5m])) by (le))
)
```

## Dashboard Investigation Guide

### During an Incident

1. **Start with API Overview**
   - Check error rate and availability
   - Note which endpoints are affected
   - Check if it's widespread or isolated

2. **Move to Service Performance**
   - Identify which services are slow/failing
   - Check service call volume for anomalies
   - Look at error distribution

3. **Check SLO Dashboard**
   - Verify error budget burn rate
   - Check if SLOs are at risk
   - Note trends over different time windows

### Post-Incident Analysis

1. Set dashboard time range to incident period
2. Create annotations for incident start/end
3. Export dashboard snapshots for reports
4. Look for leading indicators:
   - Gradual latency increase before incident
   - Error rate changes
   - Resource utilization trends

## Useful PromQL Queries

### Performance Analysis

```promql
# Request rate by endpoint
sum by (endpoint) (rate(instainstru_http_requests_total[5m]))

# Error percentage by endpoint
sum by (endpoint) (rate(instainstru_http_requests_total{status_code=~"5.."}[5m])) /
sum by (endpoint) (rate(instainstru_http_requests_total[5m])) * 100

# P50, P95, P99 latencies
histogram_quantile(0.50, sum by (le) (rate(instainstru_http_request_duration_seconds_bucket[5m])))
histogram_quantile(0.95, sum by (le) (rate(instainstru_http_request_duration_seconds_bucket[5m])))
histogram_quantile(0.99, sum by (le) (rate(instainstru_http_request_duration_seconds_bucket[5m])))
```

### Service Health

```promql
# Service operation success rate
sum by (service) (rate(instainstru_service_operation_success_total[5m])) /
(sum by (service) (rate(instainstru_service_operation_success_total[5m])) +
 sum by (service) (rate(instainstru_service_operation_errors_total[5m]))) * 100

# Services with most errors
topk(5, sum by (service, error_type) (rate(instainstru_service_operation_errors_total[5m])))

# Service operation frequency
sort_desc(sum by (service, operation) (rate(instainstru_service_operation_duration_seconds_count[5m])))
```

### Resource Usage

```promql
# Memory usage trend
process_resident_memory_bytes

# CPU usage
rate(process_cpu_seconds_total[5m])

# DB connection pool usage
(instainstru_db_pool_connections_used / instainstru_db_pool_connections_max) * 100

# Cache effectiveness
sum(rate(instainstru_cache_hits_total[5m])) /
(sum(rate(instainstru_cache_hits_total[5m])) + sum(rate(instainstru_cache_misses_total[5m]))) * 100
```

### SLO Queries

```promql
# Current error rate vs SLO
(sum(rate(instainstru_http_requests_total{status_code=~"5.."}[5m])) /
 sum(rate(instainstru_http_requests_total[5m]))) > 0.01

# Remaining error budget (30 day)
(0.001 - (sum(increase(instainstru_http_requests_total{status_code=~"5.."}[30d])) /
          sum(increase(instainstru_http_requests_total[30d])))) * 100

# Burn rate (how fast consuming error budget)
(sum(rate(instainstru_http_requests_total{status_code=~"5.."}[1h])) /
 sum(rate(instainstru_http_requests_total[1h]))) / 0.001
```

## Troubleshooting Monitoring

### Prometheus Issues

**High Memory Usage:**
```bash
# Check Prometheus memory
docker stats prometheus

# Reduce retention if needed
# Edit docker-compose.yml: --storage.tsdb.retention.time=7d
```

**Slow Queries:**
```promql
# Check query performance
prometheus_engine_query_duration_seconds{quantile="0.99"}

# Simplify queries or add recording rules
```

### Grafana Issues

**Dashboard Loading Slowly:**
1. Reduce time range
2. Limit number of series returned
3. Use recording rules for complex queries
4. Enable query caching

**Missing Data:**
1. Check datasource configuration
2. Verify Prometheus is accessible
3. Test query directly in Prometheus
4. Check time zone settings

### Metric Explosion

**Symptoms:** High cardinality warnings, OOM errors

**Solutions:**
1. Identify high cardinality metrics:
   ```promql
   topk(10, count by (__name__)({__name__=~"instainstru_.*"}))
   ```

2. Review label usage:
   - Don't use user IDs as labels
   - Limit endpoint variations
   - Use fixed label values

3. Drop unnecessary metrics:
   ```yaml
   # In prometheus.yml
   metric_relabel_configs:
     - source_labels: [__name__]
       regex: 'instainstru_temp_.*'
       action: drop
   ```

## Emergency Procedures

### Complete Monitoring Failure

1. **Fallback to application logs:**
   ```bash
   docker logs backend_app --tail 1000 -f | grep -E "ERROR|CRITICAL"
   ```

2. **Basic health checks:**
   ```bash
   # Loop health checks
   while true; do
     curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health
     echo " - $(date)"
     sleep 5
   done
   ```

3. **Manual metrics collection:**
   ```bash
   # Save metrics snapshot
   curl http://localhost:8000/metrics/prometheus > metrics-$(date +%s).txt
   ```

### Monitoring Recovery

After fixing monitoring:
1. Run validation: `python monitoring/validate-monitoring.py`
2. Check all dashboards load
3. Verify alerts can fire (use test-alerts.sh)
4. Confirm notifications work
5. Document root cause

## References

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Alerting](https://grafana.com/docs/grafana/latest/alerting/)
- [PromQL Examples](https://monitoring.mixins.dev/)
- [SRE Workbook](https://sre.google/workbook/)
