# backend/app/tasks/search_analytics.py
"""
Search analytics Celery tasks for InstaInstru.

This module contains tasks for calculating search analytics, processing
search events asynchronously, and generating search insights.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.search_event_repository import SearchEventRepository
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.search_analytics.process_search_event",
    bind=True,
    max_retries=3,
)
def process_search_event(self, event_id: int) -> Dict[str, Any]:
    """
    Process a single search event asynchronously.

    This task can be triggered after a search is performed to:
    - Enrich search data with additional analytics
    - Update aggregate metrics
    - Trigger notifications for interesting patterns

    Args:
        event_id: ID of the search event to process

    Returns:
        dict: Processing summary
    """
    db: Optional[Session] = None
    try:
        db = next(get_db())
        search_repo = SearchEventRepository(db)

        # Get the search event
        event = search_repo.get_by_id(event_id)
        if not event:
            logger.warning(f"Search event {event_id} not found")
            return {"status": "error", "message": f"Event {event_id} not found"}

        # Calculate search quality score using repository method
        quality_score = search_repo.calculate_search_quality_score(event_id)

        # Update event with calculated data
        event.quality_score = quality_score
        db.commit()

        logger.info(f"Processed search event {event_id} with quality score {quality_score}")

        return {
            "status": "success",
            "event_id": event_id,
            "quality_score": quality_score,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error(f"Failed to process search event {event_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))

    finally:
        if db:
            db.close()


@celery_app.task(
    name="app.tasks.search_analytics.calculate_search_metrics",
    bind=True,
)
def calculate_search_metrics(self, hours_back: int = 24) -> Dict[str, Any]:
    """
    Calculate aggregate search metrics for the specified time period.

    This task calculates:
    - Popular search queries
    - Search type distribution
    - Conversion rates (searches to interactions)
    - User engagement metrics

    Args:
        hours_back: Number of hours to look back (default: 24)

    Returns:
        dict: Calculated metrics
    """
    db: Optional[Session] = None
    try:
        db = next(get_db())
        search_repo = SearchEventRepository(db)

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        # Use repository methods for all data access
        popular_searches = search_repo.get_popular_searches_with_avg_results(hours=hours_back, limit=20)
        type_distribution = search_repo.get_search_type_distribution(hours=hours_back)
        total_searches = search_repo.count_searches_since(cutoff_time)
        searches_with_interactions = search_repo.count_searches_with_interactions(cutoff_time)

        conversion_rate = searches_with_interactions / total_searches * 100 if total_searches > 0 else 0

        metrics = {
            "period": {
                "start": cutoff_time.isoformat(),
                "end": datetime.now(timezone.utc).isoformat(),
                "hours": hours_back,
            },
            "popular_searches": popular_searches,
            "search_type_distribution": type_distribution,
            "engagement": {
                "total_searches": total_searches,
                "searches_with_interactions": searches_with_interactions,
                "conversion_rate": round(conversion_rate, 2),
            },
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Calculated search metrics for last {hours_back} hours")

        return metrics

    except Exception as exc:
        logger.error(f"Failed to calculate search metrics: {exc}")
        raise

    finally:
        if db:
            db.close()


@celery_app.task(
    name="app.tasks.search_analytics.generate_search_insights",
    bind=True,
)
def generate_search_insights(self, days_back: int = 7) -> Dict[str, Any]:
    """
    Generate insights from search behavior patterns.

    This task analyzes search patterns to identify:
    - Trending topics
    - Search abandonment patterns
    - Time-based search patterns
    - User journey insights

    Args:
        days_back: Number of days to analyze (default: 7)

    Returns:
        dict: Generated insights
    """
    db: Optional[Session] = None
    try:
        db = next(get_db())
        search_repo = SearchEventRepository(db)

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Calculate insights using repository methods
        total_searches = search_repo.count_searches_since(cutoff_time)
        searches_with_interactions = search_repo.count_searches_with_interactions(cutoff_time)

        # Calculate abandonment rate
        abandonment_rate = 0.0
        if total_searches > 0:
            abandonment_rate = round((total_searches - searches_with_interactions) / total_searches * 100, 2)

        # Get peak hours using repository
        try:
            peak_hours = search_repo.get_hourly_search_counts(cutoff_time, limit=5)
        except AttributeError:
            logger.exception("SearchEventRepository missing get_hourly_search_counts; returning empty peak_hours")
            peak_hours = []

        # Trending searches can be approximated using popular searches
        # In a real implementation, you'd compare time periods
        trending = search_repo.get_popular_searches(days=days_back, limit=10)

        insights = {
            "period": {
                "start": cutoff_time.isoformat(),
                "end": datetime.now(timezone.utc).isoformat(),
                "days": days_back,
            },
            "trending_searches": trending,
            "abandonment": {
                "rate": abandonment_rate,
                "description": "Percentage of searches with no follow-up interaction",
            },
            "peak_hours": peak_hours,
            "common_search_paths": [],  # Placeholder - would need session analysis
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Generated search insights for last {days_back} days")

        return insights

    except Exception as exc:
        logger.error(f"Failed to generate search insights: {exc}", exc_info=True)
        raise

    finally:
        if db:
            db.close()
