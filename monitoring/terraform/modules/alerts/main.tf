# Alerts Module - Provisions InstaInstru alert rules

variable "folder_uid" {
  description = "Grafana folder UID"
  type        = string
}

variable "datasource_uid" {
  description = "Prometheus datasource UID"
  type        = string
}

variable "contact_point_name" {
  description = "Contact point for notifications"
  type        = string
}

# Alert Rule Group
resource "grafana_rule_group" "instainstru_production" {
  name             = "InstaInstru Production Alerts"
  folder_uid       = var.folder_uid
  interval_seconds = 60

  # High Error Rate Alert
  rule {
    name      = "High Error Rate"
    condition = "B"

    data {
      ref_id = "A"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = var.datasource_uid
      model = jsonencode({
        expr         = "(sum(rate(instainstru_http_requests_total{status_code=~\"4..|5..\"}[5m])) / sum(rate(instainstru_http_requests_total[5m]))) * 100"
        refId        = "A"
        interval     = ""
        intervalMs   = 15000
        maxDataPoints = 43200
      })
    }

    data {
      ref_id = "B"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        type       = "math"
        expression = "$A > 1"
        refId      = "B"
        datasource = {
          type = "__expr__"
          uid  = "__expr__"
        }
        reducer    = "last"
        conditions = [
          {
            evaluator = {
              params = [1]
              type   = "gt"
            }
            operator = { type = "and" }
            query    = { params = ["A"] }
            type     = "query"
          }
        ]
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "3m"

    annotations = {
      summary     = "Error rate is above 1%"
      description = "The error rate is {{ $values.A.Value | printf \"%.2f\" }}% over the last 5 minutes"
      runbook_url = "https://wiki.instainstru.com/runbooks/high-error-rate"
    }

    labels = {
      severity = "critical"
      team     = "backend"
    }
  }

  # Service Degradation Alert
  rule {
    name      = "Service Degradation"
    condition = "B"

    data {
      ref_id = "A"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = var.datasource_uid
      model = jsonencode({
        expr  = "sum(rate(instainstru_http_requests_total{status_code=\"503\"}[5m])) > 0"
        refId = "A"
      })
    }

    data {
      ref_id = "B"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        type       = "math"
        expression = "$A > 0"
        refId      = "B"
        datasource = {
          type = "__expr__"
          uid  = "__expr__"
        }
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "2m"

    annotations = {
      summary     = "Service returning 503 errors"
      description = "Service is degraded and returning 503 Service Unavailable errors"
      runbook_url = "https://wiki.instainstru.com/runbooks/service-degradation"
    }

    labels = {
      severity = "critical"
      team     = "backend"
    }
  }

  # High Response Time Alert
  rule {
    name      = "High Response Time"
    condition = "B"

    data {
      ref_id = "A"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = var.datasource_uid
      model = jsonencode({
        expr  = "histogram_quantile(0.95, sum(rate(instainstru_http_request_duration_seconds_bucket[5m])) by (le))"
        refId = "A"
      })
    }

    data {
      ref_id = "B"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        type       = "math"
        expression = "$A > 0.5"
        refId      = "B"
        datasource = {
          type = "__expr__"
          uid  = "__expr__"
        }
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "5m"

    annotations = {
      summary     = "P95 response time is above 500ms"
      description = "The 95th percentile response time is {{ $values.A.Value | humanizeDuration }} over the last 5 minutes"
      runbook_url = "https://wiki.instainstru.com/runbooks/high-response-time"
    }

    labels = {
      severity = "warning"
      team     = "backend"
    }
  }

  # High Load Alert
  rule {
    name      = "High Request Load"
    condition = "B"

    data {
      ref_id = "A"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = var.datasource_uid
      model = jsonencode({
        expr  = "sum(rate(instainstru_http_requests_total[1m]))"
        refId = "A"
      })
    }

    data {
      ref_id = "B"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        type       = "math"
        expression = "$A > 1000"
        refId      = "B"
        datasource = {
          type = "__expr__"
          uid  = "__expr__"
        }
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "NoData"
    for            = "3m"

    annotations = {
      summary     = "Request rate is above 1000 req/s"
      description = "Current request rate is {{ $values.A.Value | printf \"%.0f\" }} requests per second"
      runbook_url = "https://wiki.instainstru.com/runbooks/high-load"
    }

    labels = {
      severity = "warning"
      team     = "backend"
    }
  }

  # Low Cache Hit Rate Alert
  rule {
    name      = "Low Cache Hit Rate"
    condition = "B"

    data {
      ref_id = "A"

      relative_time_range {
        from = 600
        to   = 0
      }

      datasource_uid = var.datasource_uid
      model = jsonencode({
        expr  = "sum(rate(instainstru_cache_hits_total[5m])) / (sum(rate(instainstru_cache_hits_total[5m])) + sum(rate(instainstru_cache_misses_total[5m]))) * 100"
        refId = "A"
      })
    }

    data {
      ref_id = "B"

      relative_time_range {
        from = 600
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        type       = "math"
        expression = "$A < 70"
        refId      = "B"
        datasource = {
          type = "__expr__"
          uid  = "__expr__"
        }
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "NoData"
    for            = "10m"

    annotations = {
      summary     = "Cache hit rate is below 70%"
      description = "Cache hit rate is {{ $values.A.Value | printf \"%.1f\" }}% - investigate cache configuration"
      runbook_url = "https://wiki.instainstru.com/runbooks/low-cache-hit-rate"
    }

    labels = {
      severity = "warning"
      team     = "backend"
    }
  }

  # Database Connection Pool Alert
  rule {
    name      = "Database Connection Pool Exhausted"
    condition = "B"

    data {
      ref_id = "A"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = var.datasource_uid
      model = jsonencode({
        expr  = "(instainstru_db_pool_connections_used / instainstru_db_pool_connections_max) * 100"
        refId = "A"
      })
    }

    data {
      ref_id = "B"

      relative_time_range {
        from = 300
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        type       = "math"
        expression = "$A > 90"
        refId      = "B"
        datasource = {
          type = "__expr__"
          uid  = "__expr__"
        }
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "2m"

    annotations = {
      summary     = "Database connection pool is above 90% capacity"
      description = "DB pool usage is {{ $values.A.Value | printf \"%.0f\" }}% - may cause connection timeouts"
      runbook_url = "https://wiki.instainstru.com/runbooks/db-pool-exhausted"
    }

    labels = {
      severity = "critical"
      team     = "backend"
    }
  }
}

# SLO Alert Rules
resource "grafana_rule_group" "slo_alerts" {
  name             = "InstaInstru SLO Alerts"
  folder_uid       = var.folder_uid
  interval_seconds = 300 # 5 minutes for SLO checks

  # SLO Burn Rate Alert
  rule {
    name      = "SLO Error Budget Burn Rate High"
    condition = "B"

    data {
      ref_id = "A"

      relative_time_range {
        from = 3600 # 1 hour
        to   = 0
      }

      datasource_uid = var.datasource_uid
      model = jsonencode({
        expr  = "(sum(rate(instainstru_http_requests_total{status_code=~\"5..\"}[1h])) / sum(rate(instainstru_http_requests_total[1h]))) / 0.001"
        refId = "A"
      })
    }

    data {
      ref_id = "B"

      relative_time_range {
        from = 3600
        to   = 0
      }

      datasource_uid = "__expr__"

      model = jsonencode({
        type       = "math"
        expression = "$A > 14.4" # 14.4x burn rate = 5% of monthly budget in 1 hour
        refId      = "B"
        datasource = {
          type = "__expr__"
          uid  = "__expr__"
        }
      })
    }

    no_data_state  = "NoData"
    exec_err_state = "Alerting"
    for            = "10m"

    annotations = {
      summary     = "Error budget burn rate is critically high"
      description = "Burning error budget at {{ $values.A.Value | printf \"%.1f\" }}x normal rate - will exhaust monthly budget in hours"
      runbook_url = "https://wiki.instainstru.com/runbooks/slo-burn-rate"
    }

    labels = {
      severity = "critical"
      team     = "backend"
      slo      = "availability"
    }
  }
}

# Outputs
output "rule_group_names" {
  value = [
    grafana_rule_group.instainstru_production.name,
    grafana_rule_group.slo_alerts.name
  ]
  description = "Names of created rule groups"
}
