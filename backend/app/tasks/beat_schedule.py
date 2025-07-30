# backend/app/tasks/beat_schedule.py
"""
Celery Beat schedule configuration for InstaInstru.

This module defines the periodic task schedule for the application.
Tasks are scheduled using crontab expressions for precise timing control.
"""

from datetime import timedelta

from celery.schedules import crontab

# Main beat schedule configuration
CELERYBEAT_SCHEDULE = {
    # Analytics calculation - runs every 3 hours
    "calculate-service-analytics": {
        "task": "app.tasks.analytics.calculate_analytics",
        "schedule": crontab(hour="*/3", minute=0),  # Every 3 hours
        # For testing: uncomment the line below to run every minute
        # "schedule": crontab(minute="*/1"),  # Every minute
        "args": (90,),  # Calculate analytics for last 90 days
        "kwargs": {},
        "options": {
            "queue": "analytics",
            "priority": 3,
        },
        "description": "Calculate service analytics every 3 hours",
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
        "task": "cleanup_search_history",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        "options": {
            "queue": "maintenance",
            "priority": 2,
        },
        # Note: Clean up old soft-deleted searches and expired guest sessions
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
        "description": "Calculate hourly search metrics and engagement",
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
        "description": "Generate weekly search behavior insights",
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
    "development": {
        # Override with faster intervals for testing
        "calculate-service-analytics": {
            "task": "app.tasks.analytics.calculate_analytics",
            "schedule": timedelta(minutes=5),  # Every 5 minutes for testing
            "args": (7,),  # Only last 7 days for faster execution
            "options": {
                "queue": "analytics",
                "priority": 3,
            },
        },
    },
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


def get_beat_schedule(environment: str = "production"):
    """
    Get the beat schedule for the specified environment.

    Args:
        environment: The environment name (production, development, testing)

    Returns:
        dict: The beat schedule configuration
    """
    return SCHEDULE_CONFIG.get(environment, CELERYBEAT_SCHEDULE)
