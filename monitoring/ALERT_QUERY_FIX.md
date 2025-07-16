# Alert Query Fix Documentation

## Problem
The "High Error Rate" alert was failing with the error:
> "looks like time series data, only reduced data can be alerted on"

This happens when a Prometheus query returns multiple time series instead of a single value.

## Solution Applied

### 1. Error Rate Alert
Changed from a single complex query to multiple queries with math expression:
- **Query A**: `sum(rate(instainstru_http_requests_total{status_code=~"4..|5.."}[5m]))` - Total error requests
- **Query B**: `sum(rate(instainstru_http_requests_total[5m]))` - Total requests
- **Query C**: `($A / $B) * 100` - Math expression to calculate percentage
- **Condition**: Alert when C > 1 (error rate > 1%)

### 2. Cache Hit Rate Alert
Similarly split into:
- **Query A**: Successful cache gets
- **Query B**: Total cache gets
- **Query C**: `($A / $B) * 100` - Hit rate percentage
- **Condition**: Alert when C < 60 (hit rate < 60%)

### 3. Other Alerts Verified
- **Response Time**: Uses `histogram_quantile()` which returns a single value ✓
- **Service Degradation**: Uses `max()` to reduce to single value ✓
- **High Load**: Uses `sum()` which returns a single value ✓

## Key Principles for Alert Queries

1. **Single Value Required**: Alert queries must return exactly one number, not a time series
2. **Use Aggregations**: Functions like `sum()`, `max()`, `avg()` reduce multiple series to one
3. **Math Expressions**: Use separate queries and math expressions for complex calculations
4. **Proper Conditions**: Set thresholds on the final calculated value

## Testing Your Alerts

After making changes:
```bash
# Restart Grafana to reload alerts
docker-compose -f docker-compose.monitoring.yml restart grafana

# Check logs for errors
docker-compose -f docker-compose.monitoring.yml logs grafana | grep -i alert

# Verify in UI
# Go to Alerting → Alert rules
# Check each rule shows "Normal" or "Pending" state
```

## Common Query Patterns

### Percentage Calculations
```yaml
data:
  - refId: A
    model:
      expr: sum(numerator_metric)
  - refId: B
    model:
      expr: sum(denominator_metric)
  - refId: C
    datasourceUid: __expr__
    model:
      expression: "($A / $B) * 100"
      type: math
```

### Single Value from Histogram
```yaml
expr: histogram_quantile(0.95, sum(rate(histogram_bucket[5m])) by (le))
```

### Maximum Across Services
```yaml
expr: max(your_metric_here)
```
