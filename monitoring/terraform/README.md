# Terraform Configuration for InstaInstru Monitoring

This directory contains Terraform configuration for deploying InstaInstru's monitoring infrastructure to Grafana Cloud.

## Prerequisites

1. **Grafana Cloud Account**
   - Sign up at [grafana.com](https://grafana.com/products/cloud/)
   - Create a stack in your preferred region
   - Generate API keys for Terraform

2. **Terraform**
   - Install Terraform >= 1.0
   - Configure backend for state storage (S3, GCS, etc.)

3. **Required API Keys**
   - Grafana Cloud API key (Admin role)
   - Service Account token for dashboard/alert management
   - Prometheus remote write credentials

## Quick Start

### 1. Set Up Environment Variables

Create `environments/production.tfvars`:

```hcl
# Grafana Cloud Configuration
grafana_url       = "https://yourstack.grafana.net"
grafana_api_key   = "glsa_xxxxxxxxxxxx"  # Service account token

# Prometheus Configuration
prometheus_url    = "https://prometheus-us-central1.grafana.net/api/prom"
prometheus_user   = "123456"  # Your instance ID
prometheus_api_key = "glc_xxxxxxxxxxxx"

# Alert Channels
slack_webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
alert_email_addresses = ["oncall@company.com", "engineering@company.com"]

# Environment
environment = "production"
region      = "us"
```

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Plan Changes

```bash
terraform plan -var-file=environments/production.tfvars
```

### 4. Apply Configuration

```bash
terraform apply -var-file=environments/production.tfvars
```

## What Gets Created

### Grafana Resources
- **Data Source**: Prometheus configuration for metrics
- **Folder**: "InstaInstru" folder for organizing resources
- **Dashboards**:
  - API Overview Dashboard
  - Service Performance Dashboard
  - SLO Dashboard
- **Alert Rules**:
  - High Error Rate (> 1%)
  - Service Degradation (503 errors)
  - High Response Time (P95 > 500ms)
  - High Request Load (> 1000 req/s)
  - Low Cache Hit Rate (< 70%)
  - Database Connection Pool Exhaustion (> 90%)
  - SLO Burn Rate Alert
- **Contact Points**:
  - Slack notifications
  - Email notifications
- **Notification Policy**: Routes alerts to appropriate channels

## Directory Structure

```
terraform/
├── main.tf                    # Main configuration
├── variables.tf               # Variable definitions
├── terraform.tfvars.example   # Example variables file
├── environments/              # Environment-specific configs
│   ├── production.tfvars
│   └── staging.tfvars
├── modules/                   # Reusable modules
│   ├── dashboards/           # Dashboard configurations
│   │   └── main.tf
│   └── alerts/               # Alert rule configurations
│       └── main.tf
└── README.md                 # This file
```

## Managing Multiple Environments

Create separate `.tfvars` files for each environment:

```bash
# Staging
terraform apply -var-file=environments/staging.tfvars

# Production
terraform apply -var-file=environments/production.tfvars
```

## Importing Existing Resources

If you have existing Grafana resources, import them:

```bash
# Import a dashboard
terraform import grafana_dashboard.api_overview <dashboard-uid>

# Import a folder
terraform import grafana_folder.instainstru <folder-id>

# Import a data source
terraform import grafana_data_source.prometheus <datasource-id>
```

## Backup and Recovery

### Backup Current State

```bash
# Export state to JSON
terraform show -json > state-backup-$(date +%Y%m%d).json

# Backup dashboards
for dashboard in $(terraform state list | grep grafana_dashboard); do
  terraform state show $dashboard > backups/$dashboard.json
done
```

### Disaster Recovery

1. Create new Grafana Cloud stack
2. Update `terraform.tfvars` with new endpoints
3. Run `terraform apply` to recreate all resources
4. Update application configuration with new endpoints

## Common Operations

### Update Alert Thresholds

Edit `modules/alerts/main.tf` and change the threshold values:

```hcl
model = jsonencode({
  type       = "math"
  expression = "$A > 2"  # Changed from 1 to 2
  refId      = "B"
})
```

### Add New Dashboard

Create a new dashboard resource in `modules/dashboards/main.tf`:

```hcl
resource "grafana_dashboard" "new_dashboard" {
  folder = var.folder_id

  config_json = jsonencode({
    title = "New Dashboard"
    # ... dashboard configuration
  })
}
```

### Add Alert Notification Channel

Add to `main.tf`:

```hcl
resource "grafana_contact_point" "pagerduty" {
  name = "pagerduty-critical"

  pagerduty {
    integration_key = var.pagerduty_integration_key
    severity        = "critical"
  }
}
```

## Troubleshooting

### API Authentication Errors

```
Error: failed to create dashboard: API key is invalid
```

**Solution**: Ensure you're using a Service Account token with Admin role, not a regular API key.

### Resource Already Exists

```
Error: A resource with the ID "xxx" already exists
```

**Solution**: Either import the existing resource or delete it from Grafana first.

### Rate Limiting

```
Error: API rate limit exceeded
```

**Solution**: Add delays between resource creation:

```hcl
resource "time_sleep" "wait_30_seconds" {
  depends_on = [grafana_dashboard.api_overview]
  create_duration = "30s"
}
```

## Security Best Practices

1. **Never commit `.tfvars` files** containing sensitive data
2. **Use environment variables** for API keys in CI/CD:
   ```bash
   export TF_VAR_grafana_api_key="glsa_xxxx"
   export TF_VAR_slack_webhook_url="https://hooks.slack.com/..."
   ```
3. **Enable state encryption** if using S3/GCS backend
4. **Rotate API keys** regularly and update Terraform
5. **Use separate accounts** for different environments

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy Monitoring

on:
  push:
    branches: [main]
    paths:
      - 'monitoring/terraform/**'

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.5.0

      - name: Terraform Init
        run: terraform init
        working-directory: monitoring/terraform

      - name: Terraform Apply
        env:
          TF_VAR_grafana_api_key: ${{ secrets.GRAFANA_API_KEY }}
          TF_VAR_slack_webhook_url: ${{ secrets.SLACK_WEBHOOK }}
        run: |
          terraform apply -auto-approve \
            -var-file=environments/production.tfvars
        working-directory: monitoring/terraform
```

## Maintenance

### Regular Tasks

- **Weekly**: Review alert noise, adjust thresholds
- **Monthly**: Update dashboards based on new metrics
- **Quarterly**: Review SLOs and error budgets
- **Yearly**: Audit access, rotate API keys

### Upgrading Grafana Provider

```bash
# Update provider version in main.tf
terraform init -upgrade
terraform plan
terraform apply
```

## Support

- [Grafana Cloud Documentation](https://grafana.com/docs/grafana-cloud/)
- [Terraform Grafana Provider](https://registry.terraform.io/providers/grafana/grafana/latest/docs)
- [InstaInstru Wiki](https://wiki.instainstru.com/monitoring)
