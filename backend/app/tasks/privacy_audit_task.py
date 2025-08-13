"""
Privacy Audit Celery Task - Thin wrapper for production monitoring.

This lightweight task wraps the core privacy auditor for periodic production checks.
All heavy lifting is done by app.core.privacy_auditor.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from celery import shared_task

from ..core.config import settings
from ..core.privacy_auditor import ViolationSeverity, run_privacy_audit

logger = logging.getLogger(__name__)


@shared_task(name="privacy_audit_production")
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
        return {"status": "failed", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
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
