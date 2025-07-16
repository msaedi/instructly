# Monitoring Development Guide

This guide helps developers work with the InstaInstru monitoring infrastructure.

## Table of Contents
- [Adding Metrics to Your Code](#adding-metrics-to-your-code)
- [Common PromQL Queries](#common-promql-queries)
- [Creating Custom Dashboards](#creating-custom-dashboards)
- [Performance Investigation](#performance-investigation)
- [Best Practices](#best-practices)

## Adding Metrics to Your Code

### Using @measure_operation Decorator

The `@measure_operation` decorator automatically tracks performance metrics for any service method.

#### Example: Adding to a New Service Method

```python
from app.services.base import BaseService, measure_operation

class YourService(BaseService):
    @measure_operation
    async def process_payment(self, amount: float, user_id: int) -> PaymentResult:
        """Process a payment transaction."""
        # Your business logic here
        result = await self._charge_card(amount, user_id)
        return result
```

This automatically tracks:
- Operation count
- Operation duration (with histogram buckets)
- Success/failure status
- Error types

#### Example: Adding to an Existing Service

```python
# Before
async def get_user_stats(self, user_id: int):
    stats = await self.repository.get_stats(user_id)
    return stats

# After
@measure_operation
async def get_user_stats(self, user_id: int):
    stats = await self.repository.get_stats(user_id)
    return stats
```

### What Gets Tracked

Each decorated method exposes these Prometheus metrics:
- `instainstru_service_operations_total` - Counter of operations
- `instainstru_service_operation_duration_seconds` - Histogram of durations
- `instainstru_service_operation_errors_total` - Counter of errors by type

Labels include:
- `service`: Class name (e.g., "BookingService")
- `operation`: Method name (e.g., "create_booking")
- `status`: "success" or "error"
- `error_type`: Type of exception (if error)

## Common PromQL Queries

### Performance Queries

```promql
# Average response time for a specific service
rate(instainstru_service_operation_duration_seconds_sum{service="BookingService"}[5m])
/ rate(instainstru_service_operation_duration_seconds_count{service="BookingService"}[5m])

# P95 latency across all services
histogram_quantile(0.95,
  sum by (service, operation, le) (
    rate(instainstru_service_operation_duration_seconds_bucket[5m])
  )
)

# Operations per second for a specific method
rate(instainstru_service_operations_total{
  service="AvailabilityService",
  operation="get_instructor_availability"
}[1m])

# Error rate percentage
(sum(rate(instainstru_service_operations_total{status="error"}[5m]))
/ sum(rate(instainstru_service_operations_total[5m]))) * 100
```

### Debugging Queries

```promql
# Find slowest operations in the last hour
topk(10,
  avg by (service, operation) (
    rate(instainstru_service_operation_duration_seconds_sum[1h])
    / rate(instainstru_service_operation_duration_seconds_count[1h])
  )
)

# Services with most errors
topk(5,
  sum by (service) (
    increase(instainstru_service_operation_errors_total[1h])
  )
)

# Specific error types
sum by (error_type) (
  rate(instainstru_service_operation_errors_total[5m])
) > 0
```

### Cache Performance

```promql
# Cache hit rate
sum(rate(instainstru_service_operations_total{
  service="CacheService",
  operation="get",
  status="success"
}[5m]))
/ sum(rate(instainstru_service_operations_total{
  service="CacheService",
  operation="get"
}[5m]))

# Cache operation latency
histogram_quantile(0.99,
  sum by (le) (
    rate(instainstru_service_operation_duration_seconds_bucket{
      service="CacheService"
    }[5m])
  )
)
```

## Creating Custom Dashboards

### Step 1: Design Your Dashboard

1. Access Grafana at http://localhost:3003
2. Click "+" → "Dashboard" → "Add new panel"

### Step 2: Build Queries

Example panel for booking trends:

```promql
# Bookings per hour
sum(increase(instainstru_service_operations_total{
  service="BookingService",
  operation="create_booking",
  status="success"
}[1h]))
```

### Step 3: Configure Visualization

1. Choose visualization type (Graph, Stat, Table, etc.)
2. Set panel options:
   - Title: "Bookings per Hour"
   - Unit: "short"
   - Decimals: 0

### Step 4: Save and Export

1. Save dashboard with descriptive name
2. Export JSON: Dashboard settings → JSON Model → Copy
3. Save to `monitoring/grafana/provisioning/dashboards/your-dashboard.json`

### Example: Service Health Dashboard

```json
{
  "dashboard": {
    "title": "Service Health",
    "panels": [
      {
        "title": "Service Uptime",
        "targets": [
          {
            "expr": "up{job=\"instainstru-backend\"}"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Request Rate by Service",
        "targets": [
          {
            "expr": "sum by (service) (rate(instainstru_service_operations_total[5m]))"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
```

## Performance Investigation

### 1. Identify Slow Operations

```bash
# In Prometheus console
topk(10,
  histogram_quantile(0.99,
    sum by (service, operation, le) (
      rate(instainstru_service_operation_duration_seconds_bucket[5m])
    )
  )
)
```

### 2. Check Error Patterns

Look for correlation between errors and performance:

```promql
# Error rate for slow operations
rate(instainstru_service_operation_errors_total{
  service="BookingService",
  operation="check_availability"
}[5m])
```

### 3. Analyze Trends

Use Grafana's time range selector to compare:
- Current performance vs yesterday
- Peak hours vs off-peak
- Before/after deployments

### 4. Deep Dive with Logs

Correlate metrics with application logs:

```python
# Add correlation IDs in your service
@measure_operation
async def process_request(self, request_id: str):
    logger.info(f"Processing request {request_id}")
    # ... your code
```

## Best Practices

### 1. Decorator Usage

✅ **DO:**
- Add to all public service methods
- Include async methods
- Add to methods that call external services

❌ **DON'T:**
- Add to private helper methods (starts with _)
- Add to property getters/setters
- Add to methods called in tight loops

### 2. Naming Conventions

Keep operation names clear and consistent:
- Use snake_case
- Be specific: `get_instructor_by_id` not just `get`
- Include action: `create_`, `update_`, `delete_`, `get_`, `list_`

### 3. Performance Tips

- The decorator adds ~0.1ms overhead
- Prometheus scraping adds minimal load
- Keep cardinality low (don't add user_id as label)

### 4. Testing with Metrics

```python
# In tests, metrics still work
async def test_booking_metrics():
    service = BookingService(db)
    await service.create_booking(...)  # Metrics recorded

    # Verify in test logs or use test Prometheus
```

### 5. Local Development

Monitor your local metrics:
1. Start monitoring: `./monitoring/start-monitoring.sh`
2. Make requests to your API
3. View real-time metrics in Grafana
4. Use for performance optimization

## Troubleshooting

### Metrics Not Appearing

1. Check decorator is applied:
   ```python
   # Correct
   @measure_operation
   async def my_method(self):

   # Wrong - missing decorator
   async def my_method(self):
   ```

2. Verify service inherits from BaseService:
   ```python
   class MyService(BaseService):  # Correct
   ```

3. Check Prometheus is scraping:
   - Visit http://localhost:9090/targets
   - Ensure backend target is "UP"

### High Cardinality Issues

Avoid dynamic label values:
```python
# Bad - creates too many series
metric.labels(user_id=user.id)

# Good - fixed set of labels
metric.labels(user_type="instructor")
```

### Dashboard Not Loading

1. Check JSON syntax
2. Verify datasource UID matches
3. Restart Grafana after adding dashboard

## Additional Resources

- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Grafana Dashboard Guide](https://grafana.com/docs/grafana/latest/dashboards/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- InstaInstru monitoring: `monitoring/README.md`
