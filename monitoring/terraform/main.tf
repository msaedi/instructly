terraform {
  required_version = ">= 1.0"

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = ">= 2.0"
    }
  }

  backend "s3" {
    # Configure your backend
    # bucket = "your-terraform-state-bucket"
    # key    = "monitoring/terraform.tfstate"
    # region = "us-east-1"
  }
}

# Configure the Grafana Provider
provider "grafana" {
  url  = var.grafana_url
  auth = var.grafana_api_key

  cloud_api_key = var.grafana_cloud_api_key
  sm_access_token = var.grafana_sm_access_token
}

# Create a folder for InstaInstru dashboards
resource "grafana_folder" "instainstru" {
  title = "InstaInstru"
}

# Data source for Prometheus (Grafana Cloud Metrics)
resource "grafana_data_source" "prometheus" {
  type = "prometheus"
  name = "Prometheus"
  url  = var.prometheus_url

  basic_auth_enabled  = true
  basic_auth_username = var.prometheus_user

  secure_json_data_encoded = jsonencode({
    basicAuthPassword = var.prometheus_api_key
  })

  json_data_encoded = jsonencode({
    httpMethod        = "POST"
    prometheusType    = "Mimir"
    prometheusVersion = "2.4.0"
    timeInterval      = "15s"
  })
}

# Import Slack contact point
resource "grafana_contact_point" "slack" {
  name = "slack-notifications"

  slack {
    url                     = var.slack_webhook_url
    title                   = "InstaInstru Alert"
    text                    = "{{ template \"slack.default.text\" . }}"
    disable_resolve_message = false
  }
}

# Import email contact point
resource "grafana_contact_point" "email" {
  name = "email-notifications"

  email {
    addresses               = var.alert_email_addresses
    disable_resolve_message = false
  }
}

# Configure notification policy
resource "grafana_notification_policy" "main" {
  contact_point = grafana_contact_point.slack.name
  group_by      = ["alertname"]

  group_wait      = "10s"
  group_interval  = "10s"
  repeat_interval = "1h"

  # Route critical alerts to both Slack and email
  policy {
    contact_point = grafana_contact_point.email.name
    matcher {
      label = "severity"
      match = "="
      value = "critical"
    }
    mute_timings = []

    # Also send to Slack
    policy {
      contact_point = grafana_contact_point.slack.name
      continue      = true
    }
  }

  # Route warning alerts to Slack only
  policy {
    contact_point = grafana_contact_point.slack.name
    matcher {
      label = "severity"
      match = "="
      value = "warning"
    }
  }
}

# Module for dashboards
module "dashboards" {
  source = "./modules/dashboards"

  folder_id          = grafana_folder.instainstru.id
  datasource_uid     = grafana_data_source.prometheus.uid
  grafana_url        = var.grafana_url
  grafana_api_key    = var.grafana_api_key
}

# Module for alerts
module "alerts" {
  source = "./modules/alerts"

  folder_uid         = grafana_folder.instainstru.uid
  datasource_uid     = grafana_data_source.prometheus.uid
  contact_point_name = grafana_contact_point.slack.name
}

# Outputs
output "grafana_url" {
  value       = var.grafana_url
  description = "The URL of your Grafana instance"
}

output "folder_url" {
  value       = "${var.grafana_url}/dashboards/f/${grafana_folder.instainstru.uid}"
  description = "Direct link to InstaInstru folder"
}
