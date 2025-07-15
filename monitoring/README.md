# InstaInstru Monitoring Stack

This directory contains the monitoring infrastructure for InstaInstru using Prometheus and Grafana.

## Quick Start

1. **Copy and configure environment variables:**
   ```bash
   cp .env.monitoring.example .env.monitoring
   # Edit .env.monitoring and set secure passwords
   ```

2. **Start the monitoring stack:**
   ```bash
   docker-compose -f docker-compose.monitoring.yml up -d
   ```

   Note: If you've already started the containers with default credentials,
   you may need to remove the Grafana volume and restart:
   ```bash
   docker-compose -f docker-compose.monitoring.yml down
   docker volume rm instructly_monitoring_grafana-data 2>/dev/null || true
   rm -rf ./monitoring/grafana-data
   docker-compose -f docker-compose.monitoring.yml up -d
   ```

3. **Access the services:**
   - Grafana: http://localhost:3003 (login with credentials from .env.monitoring)
   - Prometheus: http://localhost:9090

## Architecture

- **Prometheus**: Collects metrics from the FastAPI backend every 15 seconds
- **Grafana**: Visualizes metrics with dashboards and alerts
- **Persistent volumes**: Data is stored in `./monitoring/prometheus-data` and `./monitoring/grafana-data`

## Monitored Endpoints

Prometheus scrapes the following endpoints:
- `/metrics/prometheus` - Application metrics
- `/metrics/performance` - Performance metrics
- `/metrics/cache` - Cache statistics
- `/health` - Health check status

## Working with Existing Services

This monitoring stack is designed to run alongside the existing DragonflyDB container without conflicts:
- Grafana runs on port 3002 (frontend uses 3000 for HTTP, 3001 for HTTPS)
- Prometheus runs on port 9090
- Uses a separate Docker network (`instainstru_monitoring`)

## Common Commands

```bash
# View logs
docker-compose -f docker-compose.monitoring.yml logs -f

# Stop the monitoring stack
docker-compose -f docker-compose.monitoring.yml down

# Restart services
docker-compose -f docker-compose.monitoring.yml restart

# Remove volumes (WARNING: deletes all monitoring data)
docker-compose -f docker-compose.monitoring.yml down -v
```

## Creating Dashboards

1. Log into Grafana at http://localhost:3002
2. Navigate to Dashboards → New Dashboard
3. Add panels using Prometheus as the data source
4. Save dashboards to `./monitoring/grafana/provisioning/dashboards/` for persistence

## Troubleshooting

- If metrics aren't appearing, check that the backend is running on port 8000
- On macOS/Windows, Prometheus uses `host.docker.internal` to reach the host
- Check container logs: `docker-compose -f docker-compose.monitoring.yml logs prometheus`
