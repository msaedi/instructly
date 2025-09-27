#!/usr/bin/env python3
"""
Calculate analytics for service catalog from booking data.

This script analyzes existing bookings, searches, and instructor data
to populate the service_analytics table with intelligence metrics.

Usage:
    python scripts/calculate_service_analytics.py [--days-back 90]
"""

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Dict

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.booking import BookingStatus
from app.repositories.factory import RepositoryFactory

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AnalyticsCalculator:
    """Calculate and update service analytics."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.catalog_repository = RepositoryFactory.create_service_catalog_repository(db)
        self.analytics_repository = RepositoryFactory.create_service_analytics_repository(db)
        self.booking_repository = RepositoryFactory.create_booking_repository(db)

    def calculate_booking_stats(self, service_catalog_id: int, days_back: int = 90) -> Dict:
        """
        Calculate booking statistics for a service.

        Args:
            service_catalog_id: Service catalog ID
            days_back: Number of days to look back

        Returns:
            Dictionary with booking metrics
        """
        now = datetime.now(timezone.utc).date()
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)
        cutoff_all = now - timedelta(days=days_back)

        # Use repository method to get bookings
        all_bookings = self.booking_repository.get_bookings_for_service_catalog(
            service_catalog_id=service_catalog_id, from_date=cutoff_all
        )

        # Calculate counts
        count_7d = sum(1 for b in all_bookings if b.booking_date >= cutoff_7d)
        count_30d = sum(1 for b in all_bookings if b.booking_date >= cutoff_30d)

        # Calculate prices (only completed bookings)
        completed_bookings = [b for b in all_bookings if b.status == BookingStatus.COMPLETED]
        prices = [b.total_price for b in completed_bookings if b.total_price]

        stats = {
            "count_7d": count_7d,
            "count_30d": count_30d,
            "total_bookings": len(all_bookings),
            "completed_bookings": len(completed_bookings),
        }

        if prices:
            prices.sort()
            stats.update(
                {
                    "avg_price": sum(prices) / len(prices),
                    "price_p25": prices[len(prices) // 4],
                    "price_p50": prices[len(prices) // 2],
                    "price_p75": prices[3 * len(prices) // 4],
                }
            )

        # Calculate most popular duration
        duration_counts = defaultdict(int)
        for booking in completed_bookings:
            duration_counts[booking.duration_minutes] += 1

        if duration_counts:
            most_popular = max(duration_counts.items(), key=lambda x: x[1])
            stats["most_popular_duration"] = most_popular[0]
            stats["duration_distribution"] = dict(duration_counts)

        # Calculate completion rate
        if all_bookings:
            stats["completion_rate"] = len(completed_bookings) / len(all_bookings)

        # Calculate peak hours
        hour_counts = defaultdict(int)
        for booking in all_bookings:
            hour_counts[booking.start_time.hour] += 1

        if hour_counts:
            stats["peak_hours"] = dict(hour_counts)

        # Calculate peak days
        day_counts = defaultdict(int)
        for booking in all_bookings:
            day_counts[booking.booking_date.strftime("%A")] += 1

        if day_counts:
            stats["peak_days"] = dict(day_counts)

        return stats

    def calculate_instructor_stats(self, service_catalog_id: int) -> Dict:
        """
        Calculate instructor-related statistics for a service.

        Args:
            service_catalog_id: Service catalog ID

        Returns:
            Dictionary with instructor metrics
        """
        # Use repository method to count active instructors
        active_instructors = self.catalog_repository.count_active_instructors(service_catalog_id)

        # Calculate total weekly hours available
        # This is a simplified calculation - in reality would need availability data
        avg_hours_per_instructor = 20  # Assume 20 hours/week average
        total_weekly_hours = active_instructors * avg_hours_per_instructor

        return {"active_instructors": active_instructors, "total_weekly_hours": total_weekly_hours}

    def calculate_all_analytics(self, days_back: int = 90) -> int:
        """
        Calculate analytics for all services.

        Args:
            days_back: Number of days to analyze

        Returns:
            Number of services updated
        """
        # Get all active services
        services = self.catalog_repository.find_by(is_active=True)
        logger.info(f"Found {len(services)} active services to analyze")

        updated_count = 0
        for service in services:
            try:
                # Get or create analytics record
                analytics = self.analytics_repository.get_or_create(service.id)

                # Calculate booking stats
                booking_stats = self.calculate_booking_stats(service.id, days_back)

                # Calculate instructor stats
                instructor_stats = self.calculate_instructor_stats(service.id)

                # Prepare update data
                update_data = {
                    "booking_count_7d": booking_stats.get("count_7d", 0),
                    "booking_count_30d": booking_stats.get("count_30d", 0),
                    "avg_price_booked": booking_stats.get("avg_price"),
                    "price_percentile_25": booking_stats.get("price_p25"),
                    "price_percentile_50": booking_stats.get("price_p50"),
                    "price_percentile_75": booking_stats.get("price_p75"),
                    "most_booked_duration": booking_stats.get("most_popular_duration"),
                    "completion_rate": booking_stats.get("completion_rate"),
                    "active_instructors": instructor_stats["active_instructors"],
                    "total_weekly_hours": instructor_stats["total_weekly_hours"],
                    "last_calculated": datetime.now(timezone.utc),
                }

                # Store JSON data
                if "duration_distribution" in booking_stats:
                    update_data["duration_distribution"] = json.dumps(booking_stats["duration_distribution"])
                if "peak_hours" in booking_stats:
                    update_data["peak_hours"] = json.dumps(booking_stats["peak_hours"])
                if "peak_days" in booking_stats:
                    update_data["peak_days"] = json.dumps(booking_stats["peak_days"])

                # Calculate supply/demand ratio
                if booking_stats.get("count_30d", 0) > 0 and instructor_stats["total_weekly_hours"] > 0:
                    # Simplified: bookings per week / available hours per week
                    weekly_bookings = booking_stats["count_30d"] / 4.3  # Convert to weekly
                    update_data["supply_demand_ratio"] = instructor_stats["total_weekly_hours"] / weekly_bookings

                # Update analytics
                self.analytics_repository.update(analytics.service_catalog_id, **update_data)
                updated_count += 1

                logger.info(
                    f"Updated analytics for {service.name}: "
                    f"{booking_stats.get('count_30d', 0)} bookings/30d, "
                    f"{instructor_stats['active_instructors']} instructors"
                )

            except Exception as e:
                logger.error(f"Error calculating analytics for service {service.id}: {str(e)}")

        # Commits are handled by repositories automatically

        # Update display order based on new analytics
        logger.info("Updating display order based on popularity...")
        display_updates = self.catalog_repository.update_display_order_by_popularity()
        logger.info(f"Updated display order for {display_updates} services")

        # Invalidate catalog caches to reflect new order
        try:
            from app.services.cache_service import CacheService

            cache_service = CacheService(self.db)
            # Invalidate all catalog caches
            cache_service.delete_pattern("catalog:services:*")
            cache_service.delete_pattern("catalog:top-services:*")
            logger.info("Invalidated catalog caches to reflect new display order and analytics")
        except Exception as e:
            logger.warning(f"Could not invalidate cache (may not be connected): {e}")

        return updated_count

    def update_search_counts(self) -> None:
        """
        Update search counts from logs or search history.

        Note: This is a placeholder - in production, you'd read from
        search logs or a search history table.
        """
        logger.info("Updating search counts...")

        # Simulated search data - in production, read from logs
        simulated_searches = {
            "Piano Lessons": 150,
            "Guitar Lessons": 120,
            "Math Tutoring": 200,
            "SAT Prep": 180,
            "Yoga Classes": 90,
            "Personal Training": 110,
        }

        for service_name, search_count in simulated_searches.items():
            service = self.catalog_repository.find_one_by(name=service_name)
            if service:
                analytics = self.analytics_repository.get_or_create(service.id)

                # Simple simulation: 7-day count is 25% of 30-day count
                self.analytics_repository.update(
                    analytics.service_catalog_id,
                    search_count_30d=search_count,
                    search_count_7d=int(search_count * 0.25),
                )

        # Commits are handled by repositories automatically
        logger.info("Search counts updated")

    def generate_report(self) -> Dict:
        """Generate analytics summary report."""
        # Get all analytics
        all_analytics = self.analytics_repository.get_all()

        report = {
            "total_services": len(all_analytics),
            "services_with_bookings": sum(1 for a in all_analytics if a.booking_count_30d > 0),
            "services_with_searches": sum(1 for a in all_analytics if a.search_count_30d > 0),
            "total_bookings_30d": sum(a.booking_count_30d for a in all_analytics),
            "total_searches_30d": sum(a.search_count_30d for a in all_analytics),
            "services_needing_instructors": [],
            "high_demand_services": [],
            "trending_services": [],
        }

        for analytics in all_analytics:
            # Services with high demand but few instructors
            if analytics.booking_count_30d > 10 and analytics.active_instructors < 3:
                service = self.catalog_repository.get_by_id(analytics.service_catalog_id)
                if service:
                    report["services_needing_instructors"].append(
                        {
                            "name": service.name,
                            "bookings_30d": analytics.booking_count_30d,
                            "active_instructors": analytics.active_instructors,
                        }
                    )

            # High demand services
            if analytics.demand_score > 70:
                service = self.catalog_repository.get_by_id(analytics.service_catalog_id)
                if service:
                    report["high_demand_services"].append(
                        {
                            "name": service.name,
                            "demand_score": analytics.demand_score,
                            "bookings_30d": analytics.booking_count_30d,
                        }
                    )

            # Trending services
            if analytics.is_trending:
                service = self.catalog_repository.get_by_id(analytics.service_catalog_id)
                if service:
                    report["trending_services"].append(
                        {
                            "name": service.name,
                            "growth_rate": (analytics.search_count_7d / 7) / (analytics.search_count_30d / 30),
                        }
                    )

        return report


def main():
    """Main function to calculate analytics."""
    parser = argparse.ArgumentParser(description="Calculate service analytics")
    parser.add_argument("--days-back", type=int, default=90, help="Number of days to analyze (default: 90)")
    args = parser.parse_args()

    logger.info(f"Starting analytics calculation (analyzing {args.days_back} days)...")

    # Determine database URL based on environment
    if os.getenv("USE_TEST_DATABASE") == "true":
        db_url = settings.test_database_url
        logger.info("Using TEST database")
    else:
        db_url = settings.database_url
        logger.info("Using PRODUCTION database")

    # Create engine and session
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create database session
    db = SessionLocal()

    try:
        # Create calculator
        calculator = AnalyticsCalculator(db)

        # Calculate analytics
        updated_count = calculator.calculate_all_analytics(args.days_back)
        logger.info(f"Updated analytics for {updated_count} services")

        # Update search counts
        calculator.update_search_counts()

        # Generate report
        report = calculator.generate_report()

        logger.info("\n=== Analytics Report ===")
        logger.info(f"Total services analyzed: {report['total_services']}")
        logger.info(f"Services with bookings: {report['services_with_bookings']}")
        logger.info(f"Services with searches: {report['services_with_searches']}")
        logger.info(f"Total bookings (30d): {report['total_bookings_30d']}")
        logger.info(f"Total searches (30d): {report['total_searches_30d']}")

        if report["services_needing_instructors"]:
            logger.info("\nServices needing more instructors:")
            for service in report["services_needing_instructors"]:
                logger.info(
                    f"  - {service['name']}: {service['bookings_30d']} bookings, "
                    f"only {service['active_instructors']} instructors"
                )

        if report["high_demand_services"]:
            logger.info("\nHigh demand services:")
            for service in report["high_demand_services"][:5]:
                logger.info(
                    f"  - {service['name']}: demand score {service['demand_score']:.1f}, "
                    f"{service['bookings_30d']} bookings"
                )

        if report["trending_services"]:
            logger.info("\nTrending services:")
            for service in report["trending_services"][:5]:
                logger.info(f"  - {service['name']}: {service['growth_rate']:.1%} growth")

        logger.info("\nAnalytics calculation complete!")

    except Exception as e:
        logger.error(f"Error calculating analytics: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
