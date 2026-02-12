#!/usr/bin/env python3
"""
Demo of enhanced service catalog features.

Shows the three-layer architecture in action:
1. Service Catalog - WHAT services exist
2. Instructor Services - HOW they're delivered
3. Analytics - Intelligence from usage patterns
"""

import os
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.repositories.factory import RepositoryFactory


def main():
    """Run demo of enhanced catalog features."""
    print("🎯 Enhanced Service Catalog Demo\n")
    print("This demonstrates the three-layer architecture:")
    print("1. Service Catalog - Defines WHAT services exist")
    print("2. Instructor Services - Defines HOW they're delivered")
    print("3. Analytics - Provides intelligence from usage\n")

    # Setup database
    if os.getenv("USE_TEST_DATABASE") == "true":
        db_url = settings.test_database_url
        print("Using TEST database")
    else:
        db_url = settings.database_url
        print("Using PRODUCTION database")

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Create repositories
        catalog_repo = RepositoryFactory.create_service_catalog_repository(db)
        RepositoryFactory.create_service_analytics_repository(db)

        print("\n" + "=" * 60)
        print("LAYER 1: SERVICE CATALOG (What services exist)")
        print("=" * 60)

        # Show categories
        from sqlalchemy import text

        categories = db.execute(
            text(
                "SELECT sc.name, COUNT(*) as service_count FROM service_categories sc JOIN service_catalog s ON sc.id = s.category_id WHERE s.is_active = true GROUP BY sc.id, sc.name, sc.display_order ORDER BY sc.display_order"
            )
        ).fetchall()

        print("\n📚 Service Categories:")
        for cat in categories:
            print(f"  - {cat.name}: {cat.service_count} services")

        # Show service details
        print("\n📋 Sample Service (Piano Lessons):")
        piano = catalog_repo.find_one_by(slug="piano-lessons")
        if piano:
            print(f"  Name: {piano.name}")
            print(f"  Category: {piano.category.name}")
            print(f"  Description: {piano.description[:100]}...")
            print(f"  Search Terms: {', '.join(piano.search_terms or [])}")
            print(f"  Online Capable: {'Yes' if piano.online_capable else 'No'}")
            print(f"  Has Embedding: {'Yes' if piano.embedding is not None else 'No'}")

        print("\n" + "=" * 60)
        print("LAYER 2: INSTRUCTOR SERVICES (How they're delivered)")
        print("=" * 60)

        # Show instructor offerings
        instructor_services = db.execute(
            text(
                """
            SELECT
                sc.name as service_name,
                COUNT(DISTINCT ins.instructor_profile_id) as instructor_count,
                MIN(ins.hourly_rate) as min_rate,
                MAX(ins.hourly_rate) as max_rate,
                AVG(ins.hourly_rate) as avg_rate
            FROM service_catalog sc
            JOIN instructor_services ins ON sc.id = ins.service_catalog_id
            WHERE ins.is_active = true AND sc.is_active = true
            GROUP BY sc.id, sc.name
            ORDER BY instructor_count DESC
            LIMIT 10
        """
            )
        ).fetchall()

        print("\n💰 Service Pricing & Availability:")
        print(f"{'Service':<25} {'Instructors':<12} {'Price Range':<20}")
        print("-" * 60)
        for svc in instructor_services:
            price_range = f"${svc.min_rate:.0f}-${svc.max_rate:.0f} (avg ${svc.avg_rate:.0f})"
            print(f"{svc.service_name:<25} {svc.instructor_count:<12} {price_range:<20}")

        print("\n" + "=" * 60)
        print("LAYER 3: ANALYTICS (Intelligence from usage)")
        print("=" * 60)

        # Show popular services
        popular = catalog_repo.get_popular_services(limit=5, days=30)

        print("\n📊 Most Popular Services (by bookings):")
        for i, item in enumerate(popular, 1):
            service = item["service"]
            analytics = item["analytics"]
            print(f"{i}. {service.name}")
            print(f"   - {analytics.booking_count_30d} bookings/month")
            print(f"   - {analytics.search_count_30d} searches/month")
            if analytics.avg_price_booked:
                print(f"   - Average price: ${analytics.avg_price_booked:.2f}")
            if analytics.completion_rate:
                print(f"   - Completion rate: {analytics.completion_rate:.0%}")

        # Show demand insights
        print("\n🔥 Demand Insights:")

        # High demand, low supply
        high_demand = db.execute(
            text(
                """
            SELECT
                sc.name,
                sa.search_count_30d,
                sa.booking_count_30d,
                sa.active_instructors,
                sa.search_count_30d / NULLIF(sa.active_instructors, 0) as demand_per_instructor
            FROM service_catalog sc
            JOIN service_analytics sa ON sc.id = sa.service_catalog_id
            WHERE sc.is_active = true
              AND sa.search_count_30d > 10
              AND sa.active_instructors < 3
            ORDER BY demand_per_instructor DESC NULLS LAST
            LIMIT 5
        """
            )
        ).fetchall()

        if high_demand:
            print("\n⚡ High Demand, Low Supply (Opportunities):")
            for svc in high_demand:
                if svc.demand_per_instructor:
                    print(f"  - {svc.name}: {svc.search_count_30d} searches, only {svc.active_instructors} instructors")

        # Price intelligence
        print("\n💡 Price Intelligence:")
        price_insights = db.execute(
            text(
                """
            SELECT
                sc.name,
                sa.price_percentile_25_cents / 100.0 AS price_p25,
                sa.price_percentile_50_cents / 100.0 AS price_p50,
                sa.price_percentile_75_cents / 100.0 AS price_p75
            FROM service_analytics sa
            JOIN service_catalog sc ON sa.service_catalog_id = sc.id
            WHERE sa.avg_price_booked_cents IS NOT NULL
            ORDER BY sa.booking_count_30d DESC
            LIMIT 5
        """
            )
        ).fetchall()

        if price_insights:
            print(f"\n{'Service':<25} {'25th %ile':<10} {'Median':<10} {'75th %ile':<10}")
            print("-" * 55)
            for svc in price_insights:
                print(
                    f"{svc.name:<25} ${svc.price_p25:<9.0f} ${svc.price_p50:<9.0f} ${svc.price_p75:<9.0f}"
                )

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        stats = db.execute(
            text(
                """
            SELECT
                (SELECT COUNT(*) FROM service_catalog WHERE is_active = true) as total_services,
                (SELECT COUNT(DISTINCT service_catalog_id) FROM instructor_services WHERE is_active = true) as services_offered,
                (SELECT COUNT(DISTINCT instructor_profile_id) FROM instructor_services WHERE is_active = true) as active_instructors,
                (SELECT SUM(booking_count_30d) FROM service_analytics) as total_bookings,
                (SELECT SUM(search_count_30d) FROM service_analytics) as total_searches
        """
            )
        ).fetchone()

        print("\n📈 Platform Metrics:")
        print(f"  - Total services in catalog: {stats.total_services}")
        print(f"  - Services being offered: {stats.services_offered}")
        print(f"  - Active instructors: {stats.active_instructors}")
        print(f"  - Monthly bookings: {stats.total_bookings or 0}")
        print(f"  - Monthly searches: {stats.total_searches or 0}")

        print("\n✅ The three-layer architecture enables:")
        print("  1. Standardized service definitions")
        print("  2. Flexible instructor pricing and offerings")
        print("  3. Data-driven insights for growth")

    finally:
        db.close()

    print("\n🎉 Demo complete!")


if __name__ == "__main__":
    main()
