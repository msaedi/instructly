"""
Prometheus metrics endpoint for monitoring infrastructure.

This is a PUBLIC endpoint (no authentication required) following
standard Prometheus practices. It exposes metrics collected from
the @measure_operation decorators throughout the application.
"""

from fastapi import APIRouter, Response

from ..monitoring.prometheus_metrics import prometheus_metrics

router = APIRouter()


@router.get("/metrics/prometheus", include_in_schema=False, response_class=Response, response_model=None)
async def get_prometheus_metrics() -> Response:
    """
    Expose Prometheus metrics for scraping.

    This endpoint is intentionally PUBLIC (no authentication) as per
    Prometheus best practices. The metrics exposed are performance
    metrics only and do not contain sensitive business data.

    Returns:
        Response with Prometheus exposition format (text/plain)
    """
    metrics_data = prometheus_metrics.get_metrics()
    content_type = prometheus_metrics.get_content_type()

    return Response(
        content=metrics_data,
        media_type=content_type,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
    )
