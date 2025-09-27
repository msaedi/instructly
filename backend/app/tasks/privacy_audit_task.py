"""
Privacy Audit Celery Task - Thin wrapper for production monitoring.

This lightweight task wraps the core privacy auditor for periodic production checks.
All heavy lifting is done by app.core.privacy_auditor.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, ParamSpec, Protocol, TypeVar, cast

from celery import shared_task
from celery.result import AsyncResult

from ..core.config import settings
from ..core.privacy_auditor import ViolationSeverity, run_privacy_audit

logger = logging.getLogger(__name__)


P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class TaskWrapper(Protocol[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        ...

    delay: Callable[..., AsyncResult]
    apply_async: Callable[..., AsyncResult]


def typed_shared_task(
    *task_args: Any, **task_kwargs: Any
) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]:
    return cast(
        Callable[[Callable[P, R]], TaskWrapper[P, R]],
        shared_task(*task_args, **task_kwargs),
    )


@typed_shared_task(name="privacy_audit_production")
def audit_privacy_production() -> Dict[str, Any]:
    """
    Run privacy audit in production environment.

    Returns:
        Dictionary with audit summary
    """
    logger.info("Starting production privacy audit")

    # Determine API URL
    api_url = getattr(settings, "api_base_url", "https://api.instainstru.com")

    # Run async audit in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Use the core auditor
        result, _ = loop.run_until_complete(
            run_privacy_audit(
                base_url=api_url,
                test_mode=False,  # Production mode
                config_file=getattr(settings, "privacy_audit_config", None),
                verbose=False,
                output_format="json",
            )
        )

        # Count violations by severity
        high_severity = [v for v in result.violations if v.severity == ViolationSeverity.HIGH]

        # Log critical violations
        if high_severity:
            logger.error(f"PRIVACY ALERT: {len(high_severity)} high-severity violations found!")
            for v in high_severity[:5]:  # Log first 5
                logger.error(f"  - [{v.method}] {v.endpoint}: {v.message}")

        # Return summary
        return {
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "violations": {"total": len(result.violations), "high": len(high_severity)},
            "execution_time": result.execution_time,
        }

    except Exception as e:
        logger.error(f"Privacy audit failed: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        loop.close()


# Celery Beat schedule configuration
# Note: Import crontab where you configure Celery Beat (e.g., in celeryconfig.py)
# from celery.schedules import crontab
CELERY_BEAT_SCHEDULE_PRIVACY = {
    "privacy-audit-production": {
        "task": "privacy_audit_production",
        "schedule": 'crontab(minute=0, hour="*/6")',  # Every 6 hours (string for config)
        "options": {"expires": 300},  # Expire after 5 minutes
    }
}
