# Dashboard Module - Imports InstaInstru dashboards to Grafana Cloud

variable "folder_id" {
  description = "Grafana folder ID"
  type        = string
}

variable "datasource_uid" {
  description = "Prometheus datasource UID"
  type        = string
}

variable "grafana_url" {
  description = "Grafana URL"
  type        = string
}

variable "grafana_api_key" {
  description = "Grafana API key"
  type        = string
  sensitive   = true
}

# API Overview Dashboard
resource "grafana_dashboard" "api_overview" {
  folder = var.folder_id

  config_json = jsonencode({
    title = "iNSTAiNSTRU API Overview"
    uid   = "instainstru-api-overview"
    tags  = ["instainstru", "api", "overview"]

    panels = [
      # Request Rate Panel
      {
        id       = 1
        title    = "Request Rate"
        type     = "graph"
        gridPos  = { x = 0, y = 0, w = 12, h = 8 }

        targets = [
          {
            expr         = "sum(rate(instainstru_http_requests_total[5m])) by (status_code)"
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]
      },

      # Error Rate Panel
      {
        id       = 2
        title    = "Error Rate %"
        type     = "stat"
        gridPos  = { x = 12, y = 0, w = 6, h = 4 }

        targets = [
          {
            expr = <<-EOT
              sum(rate(instainstru_http_requests_total{status_code=~"5.."}[5m])) /
              sum(rate(instainstru_http_requests_total[5m])) * 100
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        fieldConfig = {
          defaults = {
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "green", value = null },
                { color = "yellow", value = 0.5 },
                { color = "red", value = 1 }
              ]
            }
            unit = "percent"
          }
        }
      },

      # Availability Panel
      {
        id       = 3
        title    = "Availability"
        type     = "stat"
        gridPos  = { x = 18, y = 0, w = 6, h = 4 }

        targets = [
          {
            expr = <<-EOT
              sum(rate(instainstru_http_requests_total{status_code!~"5.."}[5m])) /
              sum(rate(instainstru_http_requests_total[5m])) * 100
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        fieldConfig = {
          defaults = {
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "red", value = null },
                { color = "yellow", value = 99 },
                { color = "green", value = 99.9 }
              ]
            }
            unit = "percent"
          }
        }
      },

      # Response Time Panel
      {
        id       = 4
        title    = "Response Time (P95)"
        type     = "graph"
        gridPos  = { x = 0, y = 8, w = 12, h = 8 }

        targets = [
          {
            expr = <<-EOT
              histogram_quantile(0.95,
                sum(rate(instainstru_http_request_duration_seconds_bucket[5m]))
                by (le, endpoint)
              )
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
            legendFormat = "{{ endpoint }}"
          }
        ]

        fieldConfig = {
          defaults = {
            unit = "s"
          }
        }
      },

      # Active Users Panel
      {
        id       = 5
        title    = "Active Users"
        type     = "stat"
        gridPos  = { x = 12, y = 4, w = 6, h = 4 }

        targets = [
          {
            expr         = "instainstru_active_users"
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]
      },

      # Cache Hit Rate Panel
      {
        id       = 6
        title    = "Cache Hit Rate"
        type     = "gauge"
        gridPos  = { x = 18, y = 4, w = 6, h = 4 }

        targets = [
          {
            expr = <<-EOT
              sum(rate(instainstru_cache_hits_total[5m])) /
              (sum(rate(instainstru_cache_hits_total[5m])) +
               sum(rate(instainstru_cache_misses_total[5m]))) * 100
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        fieldConfig = {
          defaults = {
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "red", value = null },
                { color = "yellow", value = 60 },
                { color = "green", value = 80 }
              ]
            }
            unit = "percent"
            min  = 0
            max  = 100
          }
        }
      }
    ]

    time = {
      from = "now-6h"
      to   = "now"
    }

    refresh = "30s"
  })
}

# Service Performance Dashboard
resource "grafana_dashboard" "service_performance" {
  folder = var.folder_id

  config_json = jsonencode({
    title = "iNSTAiNSTRU Service Performance"
    uid   = "instainstru-service-performance"
    tags  = ["instainstru", "performance", "services"]

    panels = [
      # Service Operation Duration
      {
        id       = 1
        title    = "Service Operation Duration by Method"
        type     = "graph"
        gridPos  = { x = 0, y = 0, w = 12, h = 8 }

        targets = [
          {
            expr = <<-EOT
              histogram_quantile(0.95,
                sum(rate(instainstru_service_operation_duration_seconds_bucket[5m]))
                by (le, service, operation)
              )
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
            legendFormat = "{{ service }}.{{ operation }}"
          }
        ]
      },

      # Database Query Performance
      {
        id       = 2
        title    = "Database Query Performance"
        type     = "table"
        gridPos  = { x = 12, y = 0, w = 12, h = 8 }

        targets = [
          {
            expr = <<-EOT
              topk(10,
                avg by (query_type) (
                  rate(instainstru_db_query_duration_seconds_sum[5m]) /
                  rate(instainstru_db_query_duration_seconds_count[5m])
                )
              )
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
            format       = "table"
            instant      = true
          }
        ]
      },

      # Service Call Volume
      {
        id       = 3
        title    = "Service Call Volume"
        type     = "piechart"
        gridPos  = { x = 0, y = 8, w = 8, h = 8 }

        targets = [
          {
            expr = <<-EOT
              sum by (service) (
                increase(instainstru_service_operation_duration_seconds_count[1h])
              )
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]
      },

      # Error Distribution
      {
        id       = 4
        title    = "Error Distribution by Service"
        type     = "bargauge"
        gridPos  = { x = 8, y = 8, w = 8, h = 8 }

        targets = [
          {
            expr = <<-EOT
              sum by (service) (
                rate(instainstru_service_errors_total[5m])
              )
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        options = {
          orientation = "horizontal"
          displayMode = "gradient"
        }
      },

      # Memory Usage
      {
        id       = 5
        title    = "Memory Usage by Service"
        type     = "graph"
        gridPos  = { x = 16, y = 8, w = 8, h = 8 }

        targets = [
          {
            expr         = "process_resident_memory_bytes"
            refId        = "A"
            datasourceUid = var.datasource_uid
            legendFormat = "{{ job }}"
          }
        ]

        fieldConfig = {
          defaults = {
            unit = "bytes"
          }
        }
      }
    ]

    time = {
      from = "now-3h"
      to   = "now"
    }

    refresh = "1m"
  })
}

# SLO Dashboard
resource "grafana_dashboard" "slo" {
  folder = var.folder_id

  config_json = jsonencode({
    title = "iNSTAiNSTRU SLO Dashboard"
    uid   = "instainstru-slo"
    tags  = ["instainstru", "slo", "sli"]

    panels = [
      # Availability SLO
      {
        id       = 1
        title    = "Availability SLO (Target: 99.9%)"
        type     = "stat"
        gridPos  = { x = 0, y = 0, w = 6, h = 6 }

        targets = [
          {
            expr = <<-EOT
              sum(rate(instainstru_http_requests_total{status_code!~"5.."}[30d])) /
              sum(rate(instainstru_http_requests_total[30d])) * 100
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        fieldConfig = {
          defaults = {
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "red", value = null },
                { color = "yellow", value = 99.8 },
                { color = "green", value = 99.9 }
              ]
            }
            unit = "percent"
            decimals = 3
          }
        }
      },

      # Latency SLO
      {
        id       = 2
        title    = "Latency SLO (Target: P99 < 500ms)"
        type     = "stat"
        gridPos  = { x = 6, y = 0, w = 6, h = 6 }

        targets = [
          {
            expr = <<-EOT
              histogram_quantile(0.99,
                sum(rate(instainstru_http_request_duration_seconds_bucket[30d]))
                by (le)
              ) * 1000
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        fieldConfig = {
          defaults = {
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "green", value = null },
                { color = "yellow", value = 400 },
                { color = "red", value = 500 }
              ]
            }
            unit = "ms"
          }
        }
      },

      # Error Budget
      {
        id       = 3
        title    = "Error Budget Remaining (30 days)"
        type     = "gauge"
        gridPos  = { x = 12, y = 0, w = 6, h = 6 }

        targets = [
          {
            expr = <<-EOT
              (
                1 - (
                  sum(increase(instainstru_http_requests_total{status_code=~"5.."}[30d])) /
                  sum(increase(instainstru_http_requests_total[30d]))
                )
              ) - 0.999
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        fieldConfig = {
          defaults = {
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "red", value = null },
                { color = "yellow", value = 0.0005 },
                { color = "green", value = 0.001 }
              ]
            }
            unit = "percentunit"
            min  = 0
            max  = 0.001
          }
        }
      },

      # Cache Hit Rate SLO
      {
        id       = 4
        title    = "Cache Hit Rate SLO (Target: > 80%)"
        type     = "stat"
        gridPos  = { x = 18, y = 0, w = 6, h = 6 }

        targets = [
          {
            expr = <<-EOT
              sum(rate(instainstru_cache_hits_total[30d])) /
              (sum(rate(instainstru_cache_hits_total[30d])) +
               sum(rate(instainstru_cache_misses_total[30d]))) * 100
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
          }
        ]

        fieldConfig = {
          defaults = {
            thresholds = {
              mode = "absolute"
              steps = [
                { color = "red", value = null },
                { color = "yellow", value = 75 },
                { color = "green", value = 80 }
              ]
            }
            unit = "percent"
          }
        }
      },

      # SLO Burn Rate
      {
        id       = 5
        title    = "Error Budget Burn Rate"
        type     = "graph"
        gridPos  = { x = 0, y = 6, w = 24, h = 10 }

        targets = [
          {
            expr = <<-EOT
              (
                sum(rate(instainstru_http_requests_total{status_code=~"5.."}[1h])) /
                sum(rate(instainstru_http_requests_total[1h]))
              ) / 0.001
            EOT
            refId        = "A"
            datasourceUid = var.datasource_uid
            legendFormat = "Burn Rate (1x = normal)"
          }
        ]

        fieldConfig = {
          defaults = {
            custom = {
              fillOpacity = 10
              lineWidth   = 2
            }
          }
        }

        options = {
          alertThreshold = {
            visible = true
            value   = 1
          }
        }
      }
    ]

    time = {
      from = "now-30d"
      to   = "now"
    }

    refresh = "5m"
  })
}

# Outputs
output "dashboard_urls" {
  value = {
    api_overview       = "${var.grafana_url}/d/${grafana_dashboard.api_overview.uid}"
    service_performance = "${var.grafana_url}/d/${grafana_dashboard.service_performance.uid}"
    slo                = "${var.grafana_url}/d/${grafana_dashboard.slo.uid}"
  }
  description = "URLs to access the dashboards"
}
