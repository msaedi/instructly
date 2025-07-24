# Celery Setup Guide for InstaInstru

This guide covers setting up and running Celery for asynchronous task processing in the InstaInstru platform.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Running Celery Services](#running-celery-services)
- [Monitoring with Flower](#monitoring-with-flower)
- [Testing with Accelerated Schedule](#testing-with-accelerated-schedule)
- [Production Deployment on Render](#production-deployment-on-render)
- [Troubleshooting](#troubleshooting)

## Prerequisites

1. **Redis/DragonflyDB**: Celery requires a message broker. We use DragonflyDB (Redis-compatible).
2. **Python Dependencies**: Install Celery and related packages.

```bash
# Install Celery dependencies
pip install -r requirements.txt

# For additional monitoring tools
pip install -r requirements-celery.txt
```

## Local Development Setup

### 1. Start Redis/DragonflyDB

If you're using the existing DragonflyDB container:
```bash
docker start instainstru_dragonfly
```

Or start a new Redis instance:
```bash
docker run -d -p 6379:6379 --name redis redis:7-alpine
```

### 2. Configure Environment Variables

Add to your `.env` file:
```env
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 3. Directory Structure

Ensure the following structure exists:
```
backend/
├── app/
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   ├── analytics.py
│   │   ├── beat_schedule.py
│   │   └── email.py
│   └── core/
│       └── celery_config.py
```

## Running Celery Services

You'll need multiple terminal windows for full functionality:

### Terminal 1: Celery Worker
The worker processes async tasks.

```bash
cd backend
celery -A app.tasks worker --loglevel=info
```

Options:
- `--concurrency=4` - Number of worker processes (default: CPU count)
- `--queues=celery,email,analytics` - Specific queues to process
- `--loglevel=debug` - More verbose logging

### Terminal 2: Celery Beat (Scheduler)
Beat schedules periodic tasks.

```bash
cd backend
celery -A app.tasks beat --loglevel=info
```

### Terminal 3: Combined Worker + Beat (Development Only)
For development, you can run both in one process:

```bash
celery -A app.tasks worker --beat --loglevel=info
```

⚠️ **Note**: Don't use combined mode in production!

### Using Docker Compose (Recommended)

Start all services at once:
```bash
docker-compose -f docker-compose.celery.yml up -d
```

View logs:
```bash
docker-compose -f docker-compose.celery.yml logs -f celery_worker
```

## Monitoring with Flower

Flower provides a web UI for monitoring Celery tasks.

### Start Flower

```bash
celery -A app.tasks flower
```

Access at: http://localhost:5555

### Features
- Real-time task monitoring
- Worker status and statistics
- Task history and results
- Queue management
- Task rate limiting

### Secure Flower (Production)

```bash
celery -A app.tasks flower \
  --basic_auth=admin:secretpassword \
  --port=5555
```

## Testing with Accelerated Schedule

For testing periodic tasks without waiting:

### 1. Modify Beat Schedule

Edit `app/tasks/beat_schedule.py`:

```python
# Change from daily (production)
"schedule": crontab(hour=2, minute=0),  # Daily at 2 AM

# To every minute (testing)
"schedule": crontab(minute="*/1"),  # Every minute
```

### 2. Use Test Configuration

```python
# In celery_app.py or beat.py
from app.tasks.beat_schedule import get_beat_schedule

# Use testing schedule
celery_app.conf.beat_schedule = get_beat_schedule("testing")
```

### 3. Manual Task Execution

Trigger tasks manually for immediate testing:

```bash
# Via management command
python -m app.commands.analytics run

# Via Celery
python -c "from app.tasks.analytics import calculate_analytics; calculate_analytics.delay()"

# Via celery command
celery -A app.tasks call app.tasks.analytics.calculate_analytics
```

## Production Deployment on Render

### 1. Create Render Services

You'll need separate services for:
- **Worker Service**: Processes tasks
- **Beat Service**: Schedules tasks
- **Redis**: Message broker (or use Render Redis)

### 2. Worker Service Configuration

**Build Command**:
```bash
pip install -r requirements.txt
```

**Start Command**:
```bash
celery -A app.tasks worker --loglevel=info --concurrency=2
```

**Environment Variables**:
```
DATABASE_URL=<your-database-url>
REDIS_URL=<your-redis-url>
CELERY_BROKER_URL=<your-redis-url>
CELERY_RESULT_BACKEND=<your-redis-url>
```

### 3. Beat Service Configuration

**Start Command**:
```bash
celery -A app.tasks beat --loglevel=info
```

Same environment variables as Worker.

### 4. Render Blueprint Example

```yaml
services:
  # Celery Worker
  - type: worker
    name: instainstru-celery-worker
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: celery -A app.tasks worker --loglevel=info
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: instainstru-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: instainstru-redis
          property: connectionString

  # Celery Beat
  - type: worker
    name: instainstru-celery-beat
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: celery -A app.tasks beat --loglevel=info
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: instainstru-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: instainstru-redis
          property: connectionString
```

### 5. Scaling Considerations

- **Worker Scaling**: Increase worker service instances
- **Concurrency**: Adjust `--concurrency` based on service plan
- **Memory**: Monitor memory usage, set `--max-memory-per-child`
- **Queues**: Separate critical tasks into priority queues

## Troubleshooting

### Common Issues

#### 1. Worker Not Picking Up Tasks
```bash
# Check if worker is connected
celery -A app.tasks inspect active

# Check registered tasks
celery -A app.tasks inspect registered

# Check queue contents
celery -A app.tasks inspect reserved
```

#### 2. Beat Not Scheduling Tasks
```bash
# Check beat is running
ps aux | grep "celery beat"

# Check schedule
celery -A app.tasks inspect scheduled

# Delete schedule file if corrupted
rm celerybeat-schedule
```

#### 3. Redis Connection Issues
```bash
# Test Redis connection
redis-cli ping

# Check Redis is accessible
python -c "import redis; r = redis.from_url('redis://localhost:6379'); print(r.ping())"
```

#### 4. Task Failures
```python
# Check task result
from celery.result import AsyncResult
result = AsyncResult('task-id-here')
print(result.state)
print(result.info)
```

### Debugging Tips

1. **Enable Debug Logging**:
   ```bash
   celery -A app.tasks worker --loglevel=debug
   ```

2. **Run Tasks Synchronously** (for debugging):
   ```python
   # In development
   CELERY_ALWAYS_EAGER = True
   ```

3. **Monitor Redis**:
   ```bash
   redis-cli monitor
   ```

4. **Check Flower Dashboard**:
   - Failed tasks in "Tasks" tab
   - Worker status in "Workers" tab
   - Queue backlogs in "Queues" tab

### Performance Tuning

1. **Worker Pool**:
   - Use `prefork` for CPU-bound tasks
   - Use `eventlet` or `gevent` for I/O-bound tasks

2. **Concurrency**:
   ```bash
   # CPU-bound tasks
   celery worker --concurrency=4

   # I/O-bound tasks
   celery worker --pool=eventlet --concurrency=1000
   ```

3. **Task Optimization**:
   - Batch operations when possible
   - Use task routing for priority
   - Set appropriate time limits

## Additional Resources

- [Celery Documentation](https://docs.celeryproject.org/)
- [Flower Documentation](https://flower.readthedocs.io/)
- [Redis Documentation](https://redis.io/documentation)
- [Render Celery Guide](https://render.com/docs/celery)
