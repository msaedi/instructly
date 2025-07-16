# Setting Up Slack Notifications

## Current Status
The monitoring stack is configured with basic alerting. To add Slack notifications, follow these steps:

## Manual Configuration (Recommended)

Since Grafana's provisioning of contact points with environment variables can be complex, we recommend setting up Slack notifications through the UI:

### 1. Access Grafana
- Go to http://localhost:3003
- Log in with your credentials from `.env.monitoring`

### 2. Create Slack Contact Point
1. Navigate to **Alerting → Contact points**
2. Click **+ New contact point**
3. Configure:
   - **Name**: `slack-notifications`
   - **Type**: Slack
   - **Webhook URL**: Your Slack webhook URL from `.env.monitoring`
   - Click **Test** to verify
   - Click **Save contact point**

### 3. Update Notification Policies
1. Navigate to **Alerting → Notification policies**
2. Click on the default policy
3. Add new child policies:

For Critical Alerts:
- Click **+ New nested policy**
- **Matching labels**: `severity = critical`
- **Contact point**: Select both `grafana-default-email` and `slack-notifications`
- **Override grouping**: OFF
- **Override timings**: Set as needed

For Warning Alerts:
- Click **+ New nested policy**
- **Matching labels**: `severity = warning`
- **Contact point**: `slack-notifications`
- **Override grouping**: OFF
- **Override timings**: Set as needed

### 4. Test Your Setup
Run the test script to trigger alerts:
```bash
./monitoring/test-alerts.sh
```

## Why Manual Setup?

Grafana's contact point provisioning doesn't handle environment variable substitution well, especially for optional configurations. Manual setup ensures:
- Proper validation of webhook URLs
- Easy testing of notifications
- Flexibility to adjust routing rules
- No provisioning errors on startup

## Alternative: Provisioning Files

If you prefer file-based configuration, you can create contact points with hardcoded values:

1. Edit `monitoring/grafana/provisioning/alerting/contact-points.yml`
2. Replace `${SLACK_WEBHOOK_URL}` with your actual webhook
3. Restart Grafana

However, this approach requires committing sensitive webhook URLs to your repository, which is not recommended.
