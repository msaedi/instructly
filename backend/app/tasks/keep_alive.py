"""
Keep-alive tasks to prevent free tier services from spinning down.
"""

import logging
from datetime import datetime

import httpx

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.keep_alive.ping_all_services")
def ping_all_services():
    """
    Ping all services to keep them warm on Render free tier.

    Returns:
        dict: Status of each service ping
    """
    results = {"timestamp": datetime.utcnow().isoformat(), "services": {}}

    # Service endpoints to ping
    services = {
        "api": "https://instructly.onrender.com/health",
        "flower": "https://instructly-flower.onrender.com/api/workers",
        "worker": "https://instructly-celery-worker.onrender.com/health",
    }

    # Use a short timeout since we just want to wake services
    timeout = httpx.Timeout(10.0, connect=5.0)

    with httpx.Client(timeout=timeout) as client:
        for service_name, url in services.items():
            try:
                # Add auth for Flower
                if service_name == "flower":
                    response = client.get(url, auth=("admin", "1F2Z5pQHTLD9cCHcFwMwHkhMm7RJWkbM"))
                else:
                    response = client.get(url)

                results["services"][service_name] = {
                    "status": "healthy",
                    "status_code": response.status_code,
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                }
                logger.info(f"Keep-alive: {service_name} responded in {response.elapsed.total_seconds():.2f}s")

            except Exception as e:
                results["services"][service_name] = {"status": "error", "error": str(e)}
                logger.warning(f"Keep-alive: Failed to ping {service_name}: {str(e)}")

    # Also run the basic health check
    try:
        from app.tasks.celery_app import health_check

        health_result = health_check()
        results["services"]["celery_health"] = {"status": "healthy", "result": health_result}
    except Exception as e:
        results["services"]["celery_health"] = {"status": "error", "error": str(e)}

    logger.info(
        f"Keep-alive completed: {len([s for s in results['services'].values() if s['status'] == 'healthy'])}/{len(results['services'])} services healthy"
    )

    return results


@celery_app.task(name="app.tasks.keep_alive.simple_ping")
def simple_ping():
    """
    Simple ping task that just returns success.
    Useful for keeping worker active with minimal overhead.

    Returns:
        dict: Simple success response
    """
    return {
        "status": "pong",
        "timestamp": datetime.utcnow().isoformat(),
        "worker": celery_app.current_task.request.hostname,
    }
