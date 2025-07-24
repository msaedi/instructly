# Celery Tasks for InstaInstru

This directory contains all asynchronous task definitions and Celery configuration for the InstaInstru platform.

## Setup

1. Install dependencies:
```bash
pip install -r requirements-celery.txt
```

2. Ensure Redis is running:
```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or using docker-compose
docker-compose -f docker-compose.celery.yml up -d redis
```

3. Configure environment variables:
```bash
export REDIS_URL=redis://localhost:6379/0
export CELERY_TIMEZONE=US/Eastern
```

## Running Celery

### Start Worker
```bash
# Basic worker
celery -A app.tasks worker --loglevel=info

# Or with specific queues
celery -A app.tasks worker -Q celery,email,notifications --loglevel=info

# Using the worker script
python -m app.tasks.worker
```

### Start Beat Scheduler (for periodic tasks)
```bash
# Basic beat
celery -A app.tasks beat --loglevel=info

# Using the beat script
python -m app.tasks.beat
```

### Start Flower (monitoring dashboard)
```bash
celery -A app.tasks flower --port=5555

# Access at http://localhost:5555
```

### Using Docker Compose (recommended for production)
```bash
# Start all services
docker-compose -f docker-compose.celery.yml up -d

# Scale workers
docker-compose -f docker-compose.celery.yml up -d --scale celery_worker=3

# View logs
docker-compose -f docker-compose.celery.yml logs -f celery_worker
```

## Task Organization

Tasks are organized by functionality:

- `email.py` - Email sending tasks (confirmations, reminders, notifications)
- `notifications.py` - In-app notification tasks
- `analytics.py` - Analytics and reporting tasks
- `cleanup.py` - Maintenance and cleanup tasks
- `bookings.py` - Booking-related background tasks
- `cache.py` - Cache warming and maintenance

## Creating New Tasks

1. Create a new module in the `tasks` directory
2. Import and use the `BaseTask` class for automatic error handling:

```python
from app.tasks import BaseTask, celery_app

@celery_app.task(
    base=BaseTask,
    name="app.tasks.module.task_name",
    bind=True,
    max_retries=3,
)
def my_task(self, arg1, arg2):
    try:
        # Task logic here
        return {"status": "success", "result": result}
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

## Queue Configuration

Tasks are routed to specific queues based on their module:

- `celery` - Default queue for miscellaneous tasks
- `email` - Email sending tasks (priority: 5)
- `notifications` - Notification tasks (priority: 5)
- `analytics` - Analytics tasks (priority: 3)
- `maintenance` - Cleanup tasks (priority: 1)
- `bookings` - Booking-related tasks (priority: 7)
- `cache` - Cache maintenance (priority: 4)

## Periodic Tasks

Periodic tasks are configured in `celery_config.py`:

- **Hourly**: Session cleanup
- **Every 30 min**: Booking reminders
- **Daily 2 AM**: Analytics generation
- **Daily 3 AM**: Old notification cleanup
- **Every 15 min**: No-show booking checks
- **Every 5 min**: Availability cache updates
- **Every minute**: Health check

## Monitoring

### Flower Dashboard
Access at http://localhost:5555 (when running)
- Monitor task execution
- View worker status
- Inspect task results
- Manage queues

### Logging
All tasks log to the application logger with structured logging:
- Task start/completion
- Retries with reasons
- Failures with stack traces

### Metrics
Tasks include timing and success/failure metrics that can be exported to monitoring systems.

## Error Handling

The `BaseTask` class provides:
- Automatic retries with exponential backoff
- Jitter to prevent thundering herd
- Maximum retry limits
- Comprehensive error logging
- Task state tracking

## Production Considerations

1. **Worker Concurrency**: Set based on CPU cores and task types
2. **Memory Limits**: Configure `--max-memory-per-child` to prevent leaks
3. **Task Time Limits**: Both soft (warning) and hard (kill) limits are set
4. **Result Backend**: Results expire after 1 hour to prevent Redis bloat
5. **Connection Pooling**: Redis connections are pooled and reused
6. **Graceful Shutdown**: Workers finish current tasks before stopping

## Troubleshooting

### Tasks not executing
1. Check Redis connectivity: `redis-cli ping`
2. Verify worker is running: `celery -A app.tasks inspect active`
3. Check queue routing: `celery -A app.tasks inspect active_queues`

### Memory issues
1. Reduce concurrency: `--concurrency=2`
2. Set memory limits: `--max-memory-per-child=512000`
3. Use `--pool=eventlet` for I/O bound tasks

### Task failures
1. Check logs in `logs/celery/`
2. Inspect failed tasks in Flower
3. Manually retry: `celery -A app.tasks call task_name --args='[]'`
