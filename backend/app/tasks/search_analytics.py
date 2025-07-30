# backend/app/tasks/search_analytics.py
"""
Search analytics Celery tasks for InstaInstru.

This module contains tasks for calculating search analytics, processing
search events asynchronously, and generating search insights.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.search_event import SearchEvent
from app.models.search_interaction import SearchInteraction
from app.tasks.celery_app import BaseTask, celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    base=BaseTask,
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

        # Get the search event
        event = db.query(SearchEvent).filter(SearchEvent.id == event_id).first()
        if not event:
            logger.warning(f"Search event {event_id} not found")
            return {"status": "error", "message": f"Event {event_id} not found"}

        # Example processing: Calculate search quality score
        quality_score = _calculate_search_quality(db, event)

        # Update event with calculated data
        event.quality_score = quality_score
        db.commit()

        logger.info(f"Processed search event {event_id} with quality score {quality_score}")

        return {
            "status": "success",
            "event_id": event_id,
            "quality_score": quality_score,
            "processed_at": datetime.utcnow().isoformat(),
        }

    except Exception as exc:
        logger.error(f"Failed to process search event {event_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))

    finally:
        if db:
            db.close()


@celery_app.task(
    base=BaseTask,
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

        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)

        # Calculate popular searches
        popular_searches = (
            db.query(
                SearchEvent.search_query,
                func.count(SearchEvent.id).label("count"),
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .filter(SearchEvent.searched_at >= cutoff_time)
            .group_by(SearchEvent.search_query)
            .order_by(func.count(SearchEvent.id).desc())
            .limit(20)
            .all()
        )

        # Calculate search type distribution
        type_distribution = (
            db.query(
                SearchEvent.search_type,
                func.count(SearchEvent.id).label("count"),
            )
            .filter(SearchEvent.searched_at >= cutoff_time)
            .group_by(SearchEvent.search_type)
            .all()
        )

        # Calculate conversion rates
        total_searches = db.query(SearchEvent).filter(SearchEvent.searched_at >= cutoff_time).count()

        searches_with_interactions = (
            db.query(SearchEvent)
            .join(SearchInteraction)
            .filter(SearchEvent.searched_at >= cutoff_time)
            .distinct()
            .count()
        )

        conversion_rate = searches_with_interactions / total_searches * 100 if total_searches > 0 else 0

        metrics = {
            "period": {
                "start": cutoff_time.isoformat(),
                "end": datetime.utcnow().isoformat(),
                "hours": hours_back,
            },
            "popular_searches": [
                {
                    "query": query,
                    "count": count,
                    "avg_results": float(avg_results) if avg_results else 0,
                }
                for query, count, avg_results in popular_searches
            ],
            "search_type_distribution": {search_type: count for search_type, count in type_distribution},
            "engagement": {
                "total_searches": total_searches,
                "searches_with_interactions": searches_with_interactions,
                "conversion_rate": round(conversion_rate, 2),
            },
            "calculated_at": datetime.utcnow().isoformat(),
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
    base=BaseTask,
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

        cutoff_time = datetime.utcnow() - timedelta(days=days_back)

        # Find trending searches (increasing in frequency)
        trending = _find_trending_searches(db, cutoff_time)

        # Analyze search abandonment (searches with no interactions)
        abandonment_rate = _calculate_abandonment_rate(db, cutoff_time)

        # Time-based patterns (peak hours)
        peak_hours = _find_peak_search_hours(db, cutoff_time)

        # User journey patterns
        common_paths = _analyze_search_paths(db, cutoff_time)

        insights = {
            "period": {
                "start": cutoff_time.isoformat(),
                "end": datetime.utcnow().isoformat(),
                "days": days_back,
            },
            "trending_searches": trending,
            "abandonment": {
                "rate": abandonment_rate,
                "description": "Percentage of searches with no follow-up interaction",
            },
            "peak_hours": peak_hours,
            "common_search_paths": common_paths,
            "generated_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Generated search insights for last {days_back} days")

        return insights

    except Exception as exc:
        logger.error(f"Failed to generate search insights: {exc}")
        raise

    finally:
        if db:
            db.close()


def _calculate_search_quality(db: Session, event: SearchEvent) -> float:
    """
    Calculate a quality score for a search based on various factors.

    Args:
        db: Database session
        event: Search event to score

    Returns:
        float: Quality score between 0 and 100
    """
    score = 50.0  # Base score

    # Factor 1: Results count (penalize too many or too few)
    if event.results_count == 0:
        score -= 30
    elif event.results_count > 50:
        score -= 10
    elif 5 <= event.results_count <= 20:
        score += 10

    # Factor 2: Has interactions (good signal)
    has_interactions = (
        db.query(SearchInteraction).filter(SearchInteraction.search_event_id == event.id).first() is not None
    )

    if has_interactions:
        score += 20

    # Factor 3: Search type (some types are more targeted)
    if event.search_type in ["service_pill", "category"]:
        score += 5

    return max(0, min(100, score))


def _find_trending_searches(db: Session, cutoff_time: datetime) -> List[Dict[str, Any]]:
    """Find searches that are trending upward."""
    # Simplified trending detection - compare last 24h to previous 24h
    midpoint = cutoff_time + (datetime.utcnow() - cutoff_time) / 2

    recent = (
        db.query(SearchEvent.search_query, func.count(SearchEvent.id).label("count"))
        .filter(SearchEvent.searched_at >= midpoint)
        .group_by(SearchEvent.search_query)
        .subquery()
    )

    older = (
        db.query(SearchEvent.search_query, func.count(SearchEvent.id).label("count"))
        .filter(
            SearchEvent.searched_at >= cutoff_time,
            SearchEvent.searched_at < midpoint,
        )
        .group_by(SearchEvent.search_query)
        .subquery()
    )

    # This is a simplified approach - in production you'd want more sophisticated trending
    trending = []

    return trending


def _calculate_abandonment_rate(db: Session, cutoff_time: datetime) -> float:
    """Calculate the rate of searches with no follow-up interactions."""
    total_searches = db.query(SearchEvent).filter(SearchEvent.searched_at >= cutoff_time).count()

    searches_with_interactions = (
        db.query(SearchEvent).join(SearchInteraction).filter(SearchEvent.searched_at >= cutoff_time).distinct().count()
    )

    if total_searches == 0:
        return 0.0

    abandonment_rate = (total_searches - searches_with_interactions) / total_searches * 100

    return round(abandonment_rate, 2)


def _find_peak_search_hours(db: Session, cutoff_time: datetime) -> List[Dict[str, Any]]:
    """Find the hours with the most search activity."""
    hourly_counts = (
        db.query(
            func.extract("hour", SearchEvent.searched_at).label("hour"),
            func.count(SearchEvent.id).label("count"),
        )
        .filter(SearchEvent.searched_at >= cutoff_time)
        .group_by(func.extract("hour", SearchEvent.searched_at))
        .order_by(func.count(SearchEvent.id).desc())
        .limit(5)
        .all()
    )

    return [{"hour": int(hour), "search_count": count} for hour, count in hourly_counts]


def _analyze_search_paths(db: Session, cutoff_time: datetime) -> List[Dict[str, Any]]:
    """Analyze common search sequences within sessions."""
    # This is a placeholder - actual implementation would analyze session data
    # to find common search patterns (e.g., category -> specific search -> refinement)
    return []
