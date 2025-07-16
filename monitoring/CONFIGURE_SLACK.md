# Configure Slack Notifications

## Current Status
✅ Contact points are provisioned (including slack-notifications)
✅ Alerts are working
✅ Default notification policy uses default-email

## Setting Up Slack Routing

Since the notification policy provisioning has format issues, configure routing through the Grafana UI:

### 1. Access Grafana
```bash
# Make sure your .env.monitoring is sourced
source .env.monitoring

# Open Grafana
open http://localhost:3003
```

Log in with your credentials from `.env.monitoring`.

### 2. Configure Notification Routing

1. Navigate to **Alerting → Notification policies**
2. You'll see the default policy using `default-email`
3. Click the **"..."** menu → **Edit**

### 3. Add Slack Routes

Click **+ New nested policy** for each route:

**For Critical Alerts:**
- Label matchers: `severity=critical`
- Contact point: `slack-notifications`
- Continue matching subsequent sibling nodes: ✅ (if you want email too)
- Override general timings: Optional
  - Group wait: 10s
  - Group interval: 1m
  - Repeat interval: 4h

**For Warning Alerts:**
- Label matchers: `severity=warning`
- Contact point: `slack-notifications`
- Continue matching subsequent sibling nodes: ❌
- Override general timings: Optional
  - Group wait: 30s
  - Group interval: 5m
  - Repeat interval: 6h

### 4. Save Changes

Click **Save** to apply the routing rules.

## Testing

1. **Test Slack contact point:**
   - Go to **Alerting → Contact points**
   - Find `slack-notifications`
   - Click **Test**

2. **Trigger test alerts:**
   ```bash
   ./monitoring/test-alerts.sh
   ```

## Result

With this configuration:
- Critical alerts (Error Rate, Service Degradation) → Slack + Email
- Warning alerts (Response Time, High Load, Cache) → Slack only
- Other alerts → Email only

## Why Manual Configuration?

The Grafana alerting provisioning format is very strict and changes between versions. Manual configuration through the UI:
- Always works
- Provides immediate validation
- Easier to test and adjust
- No restart required
