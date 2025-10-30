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
    # ==================== FUTURE TASKS (COMMENTED) ====================
    # Booking reminders - 24 hours before appointment
    # "send-booking-reminders-24h": {
    #     "task": "app.tasks.notifications.send_booking_reminders",
    #     "schedule": crontab(minute="*/30"),  # Every 30 minutes
    #     # For testing: use timedelta(seconds=30)
    #     "kwargs": {"hours_before": 24},
    #     "options": {
    #         "queue": "notifications",
    #         "priority": 7,
    #     },
    #     "description": "Send booking reminders 24 hours in advance",
    # },
    # Booking reminders - 2 hours before appointment
    # "send-booking-reminders-2h": {
    #     "task": "app.tasks.notifications.send_booking_reminders",
    #     "schedule": crontab(minute="*/15"),  # Every 15 minutes
    #     "kwargs": {"hours_before": 2},
    #     "options": {
    #         "queue": "notifications",
    #         "priority": 8,
    #     },
    #     "description": "Send booking reminders 2 hours in advance",
    # },
    # Weekly instructor performance reports
    # "send-weekly-instructor-reports": {
    #     "task": "app.tasks.reports.send_instructor_weekly_summary",
    #     "schedule": crontab(
    #         day_of_week=1,  # Monday
    #         hour=9,         # 9 AM
    #         minute=0
    #     ),
    #     "options": {
    #         "queue": "reports",
    #         "priority": 4,
    #     },
    #     "description": "Send weekly performance summaries to instructors",
    # },
    # Monthly platform analytics report
    # "generate-monthly-platform-report": {
    #     "task": "app.tasks.reports.generate_monthly_platform_report",
    #     "schedule": crontab(
    #         day_of_month=1,  # First day of month
    #         hour=3,          # 3 AM
    #         minute=0
    #     ),
    #     "options": {
    #         "queue": "reports",
    #         "priority": 2,
    #     },
    #     "description": "Generate comprehensive monthly platform analytics",
    # },
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
    # ==================== PAYMENT PROCESSING TASKS ====================
    # Process scheduled authorizations - runs every 30 minutes
    "process-scheduled-authorizations": {
        "task": "app.tasks.payment_tasks.process_scheduled_authorizations",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "options": {
            "queue": "payments",
            "priority": 9,  # High priority - critical for payment processing
        },
        # Note: Authorize payments for bookings approaching 24-hour window
    },
    # Retry failed authorizations - runs every 2 hours
    "retry-failed-authorizations": {
        "task": "app.tasks.payment_tasks.retry_failed_authorizations",
        "schedule": crontab(minute=0, hour="*/2"),  # Every 2 hours
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
    # Cleanup old data - runs daily at 3 AM
    # "cleanup-old-notifications": {
    #     "task": "app.tasks.cleanup.cleanup_old_notifications",
    #     "schedule": crontab(hour=3, minute=0),
    #     "kwargs": {"days_to_keep": 30},
    #     "options": {
    #         "queue": "maintenance",
    #         "priority": 1,
    #     },
    #     "description": "Remove notifications older than 30 days",
    # },
    # "cleanup-expired-sessions": {
    #     "task": "app.tasks.cleanup.cleanup_expired_sessions",
    #     "schedule": crontab(minute=0),  # Every hour
    #     "options": {
    #         "queue": "maintenance",
    #         "priority": 1,
    #     },
    #     "description": "Clean up expired user sessions",
    # },
    # "cleanup-old-analytics-data": {
    #     "task": "app.tasks.cleanup.cleanup_old_analytics",
    #     "schedule": crontab(
    #         day_of_week=0,  # Sunday
    #         hour=4,         # 4 AM
    #         minute=0
    #     ),
    #     "kwargs": {"months_to_keep": 6},
    #     "options": {
    #         "queue": "maintenance",
    #         "priority": 1,
    #     },
    #     "description": "Archive analytics data older than 6 months",
    # },
    # Check for no-show bookings
    # "check-no-show-bookings": {
    #     "task": "app.tasks.bookings.check_and_mark_no_shows",
    #     "schedule": crontab(minute="*/15"),  # Every 15 minutes
    #     "options": {
    #         "queue": "bookings",
    #         "priority": 6,
    #     },
    #     "description": "Mark bookings as no-show after grace period",
    # },
    # Update availability cache
    # "warm-availability-cache": {
    #     "task": "app.tasks.cache.warm_availability_cache",
    #     "schedule": timedelta(minutes=5),  # Every 5 minutes
    #     "options": {
    #         "queue": "cache",
    #         "priority": 4,
    #     },
    #     "description": "Pre-warm availability cache for popular instructors",
    # },
    # Sync instructor calendars (if external calendar integration exists)
    # "sync-instructor-calendars": {
    #     "task": "app.tasks.calendar.sync_external_calendars",
    #     "schedule": crontab(minute="*/30"),  # Every 30 minutes
    #     "options": {
    #         "queue": "sync",
    #         "priority": 5,
    #     },
    #     "description": "Sync with Google Calendar, Calendly, etc.",
    # },
    # Health check - ensures Celery is responsive
    # "celery-health-check": {
    #     "task": "app.tasks.health_check",
    #     "schedule": timedelta(minutes=1),  # Every minute
    #     "options": {
    #         "queue": "celery",
    #         "priority": 10,
    #     },
    #     "description": "Celery worker health check",
    # },
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
