# Flower Deployment Configuration

Flower is a web-based tool for monitoring and administrating Celery clusters. This document explains how to deploy Flower on Render.

## Configuration Added to render.yaml

```yaml
- type: web
  name: instructly-flower
  runtime: python
  plan: starter  # $7/month
  buildCommand: "pip install -r requirements.txt"
  startCommand: "celery -A app.tasks.celery_app flower --port=10000 --basic_auth=$FLOWER_BASIC_AUTH"
  envVars:
    - key: PYTHON_VERSION
      value: 3.9.18
    - key: REDIS_URL
      sync: false
    - key: FLOWER_BASIC_AUTH
      sync: false
  healthCheckPath: /
  autoDeploy: false
```

## Environment Variables

Before deploying, ensure these environment variables are set in your Render dashboard:

1. **REDIS_URL**: Your Redis connection URL (same as used by Celery)
   - Example: `redis://default:password@redis-host.upstash.io:6379`

2. **FLOWER_BASIC_AUTH**: Basic authentication credentials in format `username:password`
   - Example: `admin:secure_password_here`
   - This protects your Flower dashboard from unauthorized access

## Deployment Steps

1. Commit the updated `render.yaml` to your repository
2. In Render dashboard, create a new Web Service
3. Connect it to your GitHub repository
4. Render will automatically detect the Flower service configuration
5. Set the required environment variables
6. Deploy the service

## Features

- **Web Interface**: Accessible at `https://instructly-flower.onrender.com`
- **Basic Authentication**: Protected with username/password
- **Real-time Monitoring**: View active tasks, workers, and queues
- **Task History**: Browse completed and failed tasks
- **Worker Control**: Restart workers, revoke tasks
- **Performance Metrics**: Monitor task execution times and success rates

## Cost

- Starter plan: $7/month
- Provides 512MB RAM and 0.5 CPU
- Sufficient for monitoring a small to medium Celery cluster

## Security Notes

1. Always use strong credentials for `FLOWER_BASIC_AUTH`
2. Consider IP whitelisting if Render supports it
3. Monitor access logs regularly
4. Use HTTPS (automatically provided by Render)

## Alternative Deployment (if not using render.yaml)

If you prefer to deploy Flower separately:

1. Create a new Web Service in Render
2. Set the following:
   - **Name**: instructly-flower
   - **Runtime**: Python
   - **Plan**: Starter ($7/month)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `celery -A app.tasks.celery_app flower --port=10000 --basic_auth=$FLOWER_BASIC_AUTH`
3. Add environment variables as described above
4. Deploy

## Monitoring

Once deployed, you can access Flower at your service URL. The dashboard provides:

- Active tasks and their states
- Worker status and resource usage
- Queue lengths and processing rates
- Failed task details with tracebacks
- Task execution history and statistics
