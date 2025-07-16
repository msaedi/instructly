# Grafana Cloud Configuration
variable "grafana_url" {
  description = "The URL of your Grafana Cloud instance"
  type        = string
  # Example: "https://yourstack.grafana.net"
}

variable "grafana_api_key" {
  description = "API key for Grafana Cloud (Service Account token)"
  type        = string
  sensitive   = true
}

variable "grafana_cloud_api_key" {
  description = "API key for Grafana Cloud API operations"
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_sm_access_token" {
  description = "Synthetic Monitoring access token (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

# Prometheus Configuration
variable "prometheus_url" {
  description = "URL for Grafana Cloud Prometheus endpoint"
  type        = string
  # Example: "https://prometheus-us-central1.grafana.net/api/prom"
}

variable "prometheus_user" {
  description = "Username for Prometheus (your instance ID)"
  type        = string
}

variable "prometheus_api_key" {
  description = "API key for Prometheus remote write"
  type        = string
  sensitive   = true
}

# Alert Configuration
variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  sensitive   = true
}

variable "alert_email_addresses" {
  description = "Comma-separated list of email addresses for alerts"
  type        = list(string)
  default     = ["oncall@example.com"]
}

variable "pagerduty_integration_key" {
  description = "PagerDuty integration key for critical alerts"
  type        = string
  sensitive   = true
  default     = ""
}

# Environment Configuration
variable "environment" {
  description = "Environment name (production, staging, etc.)"
  type        = string
  default     = "production"
}

variable "region" {
  description = "Cloud region for Grafana stack"
  type        = string
  default     = "us"
}

# Dashboard Configuration
variable "import_dashboards" {
  description = "Whether to import dashboards from JSON files"
  type        = bool
  default     = true
}

variable "dashboard_folder" {
  description = "Path to folder containing dashboard JSON files"
  type        = string
  default     = "../exports/dashboards"
}

# SLO Configuration
variable "slo_targets" {
  description = "SLO targets for the service"
  type = object({
    availability     = number
    latency_p99_ms  = number
    error_rate_pct  = number
    cache_hit_rate  = number
  })
  default = {
    availability    = 0.999  # 99.9%
    latency_p99_ms = 500    # 500ms
    error_rate_pct = 1      # 1%
    cache_hit_rate = 80     # 80%
  }
}

# Tags
variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    managed_by = "terraform"
    service    = "instainstru"
    component  = "monitoring"
  }
}
