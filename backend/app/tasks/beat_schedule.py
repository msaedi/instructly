# backend/app/tasks/beat_schedule.py
"""
Celery Beat schedule configuration for InstaInstru.

This module defines the periodic task schedule for the application.
Tasks are scheduled using crontab expressions for precise timing control.
"""

from datetime import timedelta
import logging
import os
from typing import Any

from celery.schedules import crontab

from app.core.config import settings

# Main beat schedule configuration
CELERYBEAT_SCHEDULE = {
    "notifications-dispatch-pending": {
        "task": "outbox.dispatch_pending",
        "schedule": timedelta(seconds=30),
        "options": {
            "queue": "notifications",
            "priority": 6,
        },
    },
    "send-booking-reminders": {
        "task": "app.tasks.notification_tasks.send_booking_reminders",
        "schedule": crontab(minute="*/15"),
        "options": {
            "queue": "notifications",
            "priority": 7,
        },
    },
    # Analytics calculation - runs at 2:30 AM and 2:30 PM (consistent across envs)
    "calculate-service-analytics": {
        "task": "app.tasks.analytics.calculate_analytics",
        "schedule": crontab(hour="3,15", minute=30),
        # For testing: uncomment the line below to run every minute
        # "schedule": crontab(minute="*/1"),  # Every minute
        "args": (90,),  # Calculate analytics for last 90 days
        "kwargs": {},
        "options": {
            "queue": "celery" if settings.environment != "production" else "analytics",
            "priority": 3,
        },
        # Note: Calculate service analytics every 3 hours
    },
    # Generate daily report - runs after analytics calculation
    "generate-daily-analytics-report": {
        "task": "app.tasks.analytics.generate_daily_report",
        "schedule": crontab(hour=2, minute=30),  # Daily at 2:30 AM
        "options": {
            "queue": "analytics",
            "priority": 3,
        },
    },
    # Codebase metrics snapshot - runs at 2:30 AM and 2:30 PM (consistent across envs)
    "append-codebase-metrics-history": {
        "task": "app.tasks.codebase_metrics.append_history",
        "schedule": crontab(hour="3,15", minute=30),
        "options": {
            "queue": "celery" if settings.environment != "production" else "analytics",
            "priority": 2,
        },
        # Note: Persists daily codebase snapshot for trend charts
    },
    "resolve-undisputed-no-shows": {
        "task": "app.tasks.payment_tasks.resolve_undisputed_no_shows",
        "schedule": crontab(minute=0),  # Every hour
        "options": {
            "queue": "celery",
            "priority": 3,
        },
    },
    "detect-video-no-shows": {
        "task": "app.tasks.video_tasks.detect_video_no_shows",
        "schedule": crontab(minute="*/15"),
        "options": {
            "queue": "celery",
            "priority": 5,
        },
    },
    # Search history cleanup - runs daily at 3 AM
    "cleanup-search-history": {
        "task": "privacy.cleanup_search_history",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        "options": {
            "queue": "privacy",
            "priority": 2,
        },
        # Note: Clean up old soft-deleted searches and expired guest sessions
    },
    # Privacy data retention - runs daily at 2 AM (before search cleanup)
    "apply-data-retention-policies": {
        "task": "privacy.apply_retention_policies",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
        "options": {
            "queue": "privacy",
            "priority": 2,
        },
        # Note: Apply GDPR data retention policies across all data types
    },
    # Privacy compliance report - runs weekly on Sunday at 1 AM
    "generate-privacy-report": {
        "task": "privacy.generate_privacy_report",
        "schedule": crontab(day_of_week=0, hour=1, minute=0),  # Sunday  # 1 AM
        "options": {
            "queue": "privacy",
            "priority": 1,
        },
        # Note: Generate weekly privacy compliance statistics
    },
    # Calculate search metrics - runs every hour
    "calculate-search-metrics": {
        "task": "app.tasks.search_analytics.calculate_search_metrics",
        "schedule": crontab(minute=0),  # Every hour at :00
        "kwargs": {"hours_back": 24},  # Last 24 hours
        "options": {
            "queue": "analytics",
            "priority": 4,
        },
        # Note: Calculate hourly search metrics and engagement
    },
    # DB maintenance — refresh query-planner statistics on high-churn tables
    "db-maintenance-analyze": {
        "task": "db_maintenance.analyze_high_churn_tables",
        "schedule": crontab(hour=4, minute=0),  # Daily at 4 AM UTC
        "options": {
            "queue": "celery",
            "priority": 1,
        },
    },
    # DB maintenance — purge abandoned 2FA setup secrets (AUTHZ-VULN-04 defense-in-depth)
    "cleanup-stale-2fa-setups": {
        "task": "db_maintenance.cleanup_stale_2fa_setups",
        "schedule": crontab(hour=5, minute=0),  # Daily at 5 AM UTC
        "options": {
            "queue": "celery",
            "priority": 1,
        },
    },
    # Self-learning: promote unresolved location queries into trusted aliases
    "learn-location-aliases": {
        "task": "app.tasks.location_learning.process_location_learning",
        "schedule": crontab(hour=3, minute=10),  # Daily at 3:10 AM
        "kwargs": {"limit": 500},
        "options": {
            "queue": "analytics",
            "priority": 3,
        },
    },
    # ==================== PAYMENT PROCESSING TASKS ====================
    # Process scheduled authorizations - runs every 5 minutes
    "process-scheduled-authorizations": {
        "task": "app.tasks.payment_tasks.process_scheduled_authorizations",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
        "options": {
            "queue": "payments",
            "priority": 9,  # High priority - critical for payment processing
        },
        # Note: Authorize payments for bookings approaching 24-hour window
    },
    # Retry failed authorizations - runs every 15 minutes
    "retry-failed-authorizations": {
        "task": "app.tasks.payment_tasks.retry_failed_authorizations",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {
            "queue": "payments",
            "priority": 8,
        },
        # Note: Retry failed payment authorizations with exponential backoff
    },
    # Capture completed lessons - runs every hour
    "capture-completed-lessons": {
        "task": "app.tasks.payment_tasks.capture_completed_lessons",
        "schedule": crontab(minute=0),  # Every hour
        "options": {
            "queue": "payments",
            "priority": 7,
        },
        # Note: Capture pre-authorized payments for completed lessons
    },
    # Retry failed captures - runs every 4 hours
    "retry-failed-captures": {
        "task": "app.tasks.payment_tasks.retry_failed_captures",
        "schedule": crontab(minute=0, hour="*/4"),  # Every 4 hours
        "options": {
            "queue": "payments",
            "priority": 6,
        },
        # Note: Retry captures that failed after lesson completion
    },
    # Payment system health check - runs every 15 minutes
    "payment-health-check": {
        "task": "app.tasks.payment_tasks.check_authorization_health",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {
            "queue": "payments",
            "priority": 10,  # Highest priority - monitoring critical
        },
        # Note: Dead man's switch - alerts if payment jobs aren't running
    },
    # Nightly payout schedule audit - ensures all accounts are on weekly Tuesday
    "payout-schedule-audit": {
        "task": "app.tasks.payment_tasks.audit_and_fix_payout_schedules",
        "schedule": crontab(minute=0, hour=3),  # 3 AM UTC nightly
        "options": {
            "queue": "payments",
            "priority": 5,
        },
        # Note: Calls StripeService.set_payout_schedule_for_account for any mismatches
    },
    # Generate search insights - runs daily at 4 AM
    "generate-search-insights": {
        "task": "app.tasks.search_analytics.generate_search_insights",
        "schedule": crontab(hour=4, minute=0),  # Daily at 4 AM
        "kwargs": {"days_back": 7},  # Last 7 days
        "options": {
            "queue": "analytics",
            "priority": 3,
        },
        # Note: Generate weekly search behavior insights
    },
    # ==================== EMBEDDING MAINTENANCE ====================
    # Maintain service embeddings - runs every hour
    "maintain-service-embeddings": {
        "task": "maintain_service_embeddings",
        "schedule": crontab(minute=30),  # Every hour at :30
        "options": {
            "queue": "analytics",
            "priority": 3,
        },
        # Note: Update embeddings for new/changed services
    },
    # Finalize pending badges daily (after quality holds expire)
    "badges-finalize-pending": {
        "task": "badges.finalize_pending",
        "schedule": crontab(hour=7, minute=0),  # Daily at 07:00 UTC
        "options": {
            "queue": "analytics",
            "priority": 4,
        },
    },
    "referrals-unlock-every-15m": {
        "task": "app.tasks.referrals.run_unlocker",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {
            "queue": "celery",
            "priority": 5,
        },
        # Note: Unlock pending referral rewards on a rolling cadence
    },
    # Instructor referral payouts
    "retry-failed-instructor-referral-payouts": {
        "task": "app.tasks.referral_tasks.retry_failed_instructor_referral_payouts",
        "schedule": crontab(minute=0),  # Every hour at :00
        "options": {
            "queue": "payments",
            "priority": 6,
        },
    },
    "check-pending-instructor-referral-payouts": {
        "task": "app.tasks.referral_tasks.check_pending_instructor_referral_payouts",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {
            "queue": "payments",
            "priority": 6,
        },
    },
}

# Schedule configuration for different environments
SCHEDULE_CONFIG = {
    "production": CELERYBEAT_SCHEDULE,
    "testing": {
        # Minimal schedule for test environment
        "test-analytics": {
            "task": "app.tasks.analytics.calculate_analytics",
            "schedule": timedelta(seconds=30),  # Very frequent for testing
            "args": (1,),  # Only 1 day of data
            "options": {
                "queue": "analytics",
                "priority": 10,
            },
        },
    },
}


def _parse_cron_expression(cron_expr: str) -> Any:
    """Convert a five-field cron expression into a Celery crontab schedule."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        logging.getLogger(__name__).warning(
            "Invalid RETENTION_PURGE_CRON expression '%s'; falling back to 0 4 * * *",
            cron_expr,
        )
        parts = ["0", "4", "*", "*", "*"]
    minute, hour, day_of_month, month_of_year, day_of_week = parts
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


def get_beat_schedule(environment: str = "production") -> dict[str, dict[str, Any]]:
    """
    Get the beat schedule for the specified environment.

    Args:
        environment: The environment name (production, development, testing)

    Returns:
        Mapping of task name to Celery beat configuration dict
    """
    # Start from the base schedule, then apply environment-specific overrides
    base: dict[str, dict[str, Any]] = dict(CELERYBEAT_SCHEDULE)
    overrides = SCHEDULE_CONFIG.get(environment)
    if overrides:
        base.update(overrides)
    retention_cron = os.getenv("RETENTION_PURGE_CRON", "0 4 * * *")
    retention_queue = os.getenv("CELERY_RETENTION_QUEUE", "maintenance")
    base["nightly-retention-purge"] = {
        "task": "retention.purge_soft_deleted",
        "schedule": _parse_cron_expression(retention_cron),
        "args": [],
        "kwargs": {},
        "options": {
            "queue": retention_queue,
            "priority": 2,
        },
    }
    return base
