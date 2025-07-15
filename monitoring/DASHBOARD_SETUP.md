# InstaInstru Dashboard Provisioning Setup

## ✅ Current Configuration

The dashboard provisioning is fully configured and ready:

### 1. Dashboard Location
- **Path**: `monitoring/grafana/provisioning/dashboards/`
- **Files**:
  - `service-performance.json` - Service Performance Dashboard
  - `api-health.json` - API Health Dashboard
  - `business-metrics.json` - Business Metrics Dashboard

### 2. Provisioning Configuration
**File**: `monitoring/grafana/provisioning/dashboards/dashboard.yml`

```yaml
apiVersion: 1
providers:
  - name: 'InstaInstru Dashboards'
    orgId: 1
    folder: 'InstaInstru'           # Creates folder in Grafana
    folderUid: 'instainstru'        # Unique folder ID
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10        # Checks for updates every 10s
    allowUiUpdates: true            # Allows editing in Grafana UI
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: false
```

### 3. Docker Volume Mapping
The `docker-compose.monitoring.yml` maps the local directory to Grafana:
```yaml
volumes:
  - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
```

### 4. Auto-Refresh Settings
All dashboards are configured with 30-second auto-refresh:
- Service Performance: ✅ 30s refresh
- API Health: ✅ 30s refresh
- Business Metrics: ✅ 30s refresh

## How It Works

1. When Grafana starts, it reads `dashboard.yml`
2. It looks for JSON files in the specified path
3. Creates an "InstaInstru" folder in Grafana
4. Loads all three dashboards into that folder
5. Dashboards auto-refresh every 30 seconds

## To Apply Changes

If you've already started Grafana:
```bash
# Restart Grafana to reload dashboards
docker-compose -f docker-compose.monitoring.yml restart grafana

# Or restart the entire monitoring stack
docker-compose -f docker-compose.monitoring.yml down
docker-compose -f docker-compose.monitoring.yml up -d
```

## Verify Setup

1. Access Grafana: http://localhost:3003
2. Login with credentials from `.env.monitoring`
3. Navigate to Dashboards
4. Look for "InstaInstru" folder
5. All three dashboards should be available

## Troubleshooting

If dashboards don't appear:
- Check Grafana logs: `docker-compose -f docker-compose.monitoring.yml logs grafana`
- Verify JSON files exist: `ls monitoring/grafana/provisioning/dashboards/*.json`
- Ensure proper permissions on files
- Check for JSON syntax errors in dashboard files
