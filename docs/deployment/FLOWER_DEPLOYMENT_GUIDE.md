# Deploying Flower on Render

Flower provides a web-based tool for monitoring and administrating Celery clusters.

## Setup Steps

### 1. Deploy to Render

1. **Go to Render Dashboard**
   - Click "New +" → "Web Service"
   - Connect your GitHub repo

2. **Configure the Service**:
   - **Name**: `instructly-flower`
   - **Environment**: `Docker`
   - **Dockerfile Path**: `./Dockerfile.flower`
   - **Docker Context**: `.`
   - **Plan**: Free (or Starter for $7/month)

3. **Add Environment Variables**:
   ```
   REDIS_URL = [same as your main app's Redis URL]
   FLOWER_BASIC_AUTH = admin:your-secure-password-here
   ```

4. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment (3-5 minutes)

### 2. Access Flower

Once deployed, you'll get a URL like:
```
https://instructly-flower.onrender.com
```

Login with the credentials you set in `FLOWER_BASIC_AUTH`.

## Features You'll See

1. **Dashboard**: Overview of workers, tasks, and queues
2. **Tasks**: List of all tasks with status, runtime, args
3. **Workers**: Active Celery workers and their status
4. **Queues**: Message queues and their lengths
5. **Monitor**: Real-time task execution graphs

## Security Notes

1. **Always use authentication** in production
2. **Use HTTPS** (Render provides this automatically)
3. **Choose a strong password** for FLOWER_BASIC_AUTH
4. **Restrict access** by IP if possible (Render Pro feature)

## Alternative: Command Line Deployment

```bash
# Using Render CLI
render blueprint launch --file render-flower.yaml
```

## Monitoring Your Alerts

In Flower, you'll see:
- `process_monitoring_alert` tasks
- `send_alert_email` tasks
- `create_github_issue_for_alert` tasks
- Task success/failure rates
- Execution times
- Retry attempts

## Troubleshooting

If Flower doesn't show tasks:
1. Check Redis connection
2. Verify workers are running
3. Check task registration in logs
4. Ensure same Redis database (default: 0)

## Cost

- **Free tier**: Works fine for monitoring
- **Starter ($7/month)**: Better performance, custom domain
- **No additional infrastructure needed** - uses same Redis as your app
