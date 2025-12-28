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

        Optimized version: uses bulk loading to reduce ~1,250 queries to ~6.

        Args:
            days_back: Number of days to analyze

        Returns:
            Number of services updated
        """
        # Get all active services
        services = self.catalog_repository.find_by(is_active=True)
        service_ids = [s.id for s in services]
        logger.info(f"Found {len(services)} active services to analyze")

        if not service_ids:
            return 0

        # Calculate date ranges once
        now = datetime.now(timezone.utc).date()
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)
        cutoff_all = now - timedelta(days=days_back)

        # BULK LOAD 1: Get all bookings grouped by service_catalog_id (1 query)
        bookings_by_service = self.booking_repository.get_all_bookings_by_service_catalog(
            from_date=cutoff_all, to_date=now
        )
        logger.info(f"Loaded bookings for {len(bookings_by_service)} services in 1 query")

        # BULK LOAD 2: Get all instructor counts (1 query)
        instructor_counts = self.catalog_repository.count_active_instructors_bulk(service_ids)
        logger.info(f"Loaded instructor counts for {len(instructor_counts)} services in 1 query")

        # BULK LOAD 3: Get or create all analytics records (1-2 queries)
        analytics_map = self.analytics_repository.get_or_create_bulk(service_ids)
        logger.info(f"Loaded/created {len(analytics_map)} analytics records")

        # Calculate all stats in memory (no DB queries)
        all_updates = []
        calculation_time = datetime.now(timezone.utc)

        for service_id in service_ids:
            try:
                all_bookings = bookings_by_service.get(service_id, [])
                active_instructors = instructor_counts.get(service_id, 0)

                # Calculate booking stats from pre-loaded data
                count_7d = sum(1 for b in all_bookings if b.booking_date >= cutoff_7d)
                count_30d = sum(1 for b in all_bookings if b.booking_date >= cutoff_30d)

                completed_bookings = [b for b in all_bookings if b.status == BookingStatus.COMPLETED]
                prices = [b.total_price for b in completed_bookings if b.total_price]

                # Instructor stats
                avg_hours_per_instructor = 20
                total_weekly_hours = active_instructors * avg_hours_per_instructor

                # Prepare update data
                update_data: Dict[str, object] = {
                    "service_catalog_id": service_id,
                    "booking_count_7d": count_7d,
                    "booking_count_30d": count_30d,
                    "active_instructors": active_instructors,
                    "total_weekly_hours": total_weekly_hours,
                    "last_calculated": calculation_time,
                }

                # Price stats
                if prices:
                    prices.sort()
                    update_data["avg_price_booked"] = sum(prices) / len(prices)
                    update_data["price_percentile_25"] = prices[len(prices) // 4]
                    update_data["price_percentile_50"] = prices[len(prices) // 2]
                    update_data["price_percentile_75"] = prices[3 * len(prices) // 4]

                # Duration stats
                duration_counts: Dict[int, int] = defaultdict(int)
                for booking in completed_bookings:
                    duration_counts[booking.duration_minutes] += 1
                if duration_counts:
                    most_popular = max(duration_counts.items(), key=lambda x: x[1])
                    update_data["most_booked_duration"] = most_popular[0]
                    update_data["duration_distribution"] = json.dumps(dict(duration_counts))

                # Completion rate
                if all_bookings:
                    update_data["completion_rate"] = len(completed_bookings) / len(all_bookings)

                # Peak hours
                hour_counts: Dict[int, int] = defaultdict(int)
                for booking in all_bookings:
                    hour_counts[booking.start_time.hour] += 1
                if hour_counts:
                    update_data["peak_hours"] = json.dumps(dict(hour_counts))

                # Peak days
                day_counts: Dict[str, int] = defaultdict(int)
                for booking in all_bookings:
                    day_counts[booking.booking_date.strftime("%A")] += 1
                if day_counts:
                    update_data["peak_days"] = json.dumps(dict(day_counts))

                # Supply/demand ratio
                if count_30d > 0 and total_weekly_hours > 0:
                    weekly_bookings = count_30d / 4.3
                    update_data["supply_demand_ratio"] = total_weekly_hours / weekly_bookings

                all_updates.append(update_data)

            except Exception as e:
                logger.error(f"Error calculating analytics for service {service_id}: {str(e)}")

        # BULK UPDATE: Update all analytics in one operation (1 round trip with native SQL)
        updated_count = self.analytics_repository.bulk_update_all(all_updates)
        self.db.commit()
        logger.info(f"Bulk updated {updated_count} analytics records (native SQL)")

        # Update display order based on new analytics (1 round trip with native SQL)
        logger.info("Updating display order based on popularity...")
        display_updates = self.catalog_repository.update_display_order_by_popularity()
        self.db.commit()
        logger.info(f"Updated display order for {display_updates} services (native SQL)")

        # Invalidate catalog caches to reflect new order
        try:
            from app.services.cache_service import CacheService, CacheServiceSyncAdapter

            cache_service = CacheServiceSyncAdapter(CacheService(self.db))
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

        # Pre-load all services by name in ONE query
        service_names = list(simulated_searches.keys())
        all_services = self.catalog_repository.find_by(is_active=True)
        name_to_service = {s.name: s for s in all_services}

        # Pre-load all analytics in ONE query
        service_ids = [name_to_service[name].id for name in service_names if name in name_to_service]
        analytics_map = self.analytics_repository.get_or_create_bulk(service_ids)

        # Update in memory
        for service_name, search_count in simulated_searches.items():
            service = name_to_service.get(service_name)
            if service and service.id in analytics_map:
                analytics = analytics_map[service.id]
                analytics.search_count_30d = search_count
                analytics.search_count_7d = int(search_count * 0.25)

        self.db.flush()
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
        label = "PRODUCTION" if settings.is_production_database(db_url) else "NON-PROD"
        logger.info("Using %s database", label)

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
