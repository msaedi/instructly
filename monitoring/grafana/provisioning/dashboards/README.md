# InstaInstru Grafana Dashboards

This directory contains production-ready Grafana dashboards for monitoring InstaInstru.

## Available Dashboards

### 1. Service Performance Dashboard
**File**: `service-performance.json`
**UID**: `instainstru-service-performance`

Monitors the performance of all InstaInstru services using @measure_operation metrics:
- **Service Response Time**: Line graph showing average response times per service/operation
- **Top 10 Slowest Operations**: Table showing P95 latency for slowest operations
- **Operations per Second by Service**: Bar chart showing throughput by service
- **Service Call Distribution**: Pie chart showing which services are called most
- **Operation Latency Heatmap**: Visual distribution of operation latencies over time
- **Anomaly Detection**: Z-score analysis highlighting unusual performance spikes (Z > 3)
- **SLA Compliance**: Percentage of requests completing under 500ms target
- **Service Activity Map**: Node graph showing service activity levels

**Variables**:
- `$service`: Filter by specific service(s)
- `$operation`: Filter by specific operation(s)

### 2. API Health Dashboard
**File**: `api-health.json`
**UID**: `instainstru-api-health`

Tracks HTTP request metrics and API health:
- **HTTP Request Rate**: Total and per-method request rates
- **HTTP Error Rate**: 4xx and 5xx errors with percentage
- **Response Time Percentiles**: P50, P90, P95, P99 latencies
- **Current Active Requests**: Real-time count of in-flight requests
- **Endpoint Performance Table**: Average response time per endpoint

**Features**:
- Alert annotation when error rate exceeds 1%
- 10-second refresh for real-time monitoring

### 3. Business Metrics Dashboard
**File**: `business-metrics.json`
**UID**: `instainstru-business-metrics`

Focuses on business-relevant metrics:
- **Booking Operations**: Track all booking service operations
- **Instructor Service Operations**: Monitor instructor-related activities
- **Cache Performance**: Gauge showing cache hit rate
- **Most Active Services**: Bar chart of operations per hour
- **Operation Success Rate**: Overall platform reliability percentage
- **Service Usage Distribution**: 24-hour usage breakdown

## Usage

These dashboards are automatically provisioned when Grafana starts. They will appear in the "InstaInstru" folder in Grafana.

### Accessing Dashboards

1. Navigate to Grafana at http://localhost:3003
2. Click on "Dashboards" in the left menu
3. Open the "InstaInstru" folder
4. Select the dashboard you want to view

### Time Ranges

All dashboards default to "Last 6 hours" but can be adjusted using Grafana's time picker.

### Customization

The dashboards are configured with `allowUiUpdates: true`, so you can:
- Modify panels
- Add new visualizations
- Save changes (they'll persist in the JSON files)

## Metrics Used

The dashboards use these Prometheus metrics:
- `instainstru_service_operation_duration_seconds` - Service method performance
- `instainstru_service_operations_total` - Operation counts
- `instainstru_http_request_duration_seconds` - HTTP request latency
- `instainstru_http_requests_total` - HTTP request counts
- `instainstru_http_requests_in_progress` - Active request gauge
- `instainstru_errors_total` - Error counts (if available)

## Best Practices

1. **Regular Monitoring**: Check the API Health dashboard for error spikes
2. **Performance Tracking**: Use Service Performance to identify slow operations
3. **Business Insights**: Review Business Metrics for usage patterns
4. **Alert Setup**: Configure alerts based on the metrics shown

## Troubleshooting

If dashboards don't appear:
1. Check Grafana logs: `docker-compose -f docker-compose.monitoring.yml logs grafana`
2. Verify Prometheus is scraping: http://localhost:9090/targets
3. Ensure the backend is running and exposing metrics at `/metrics/prometheus`
