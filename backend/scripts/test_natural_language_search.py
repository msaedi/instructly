#!/usr/bin/env python3
"""
Test natural language search functionality.

This script demonstrates the enhanced search capabilities including:
- Semantic search using embeddings
- Natural language query parsing
- Multi-filter search with analytics
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.search_service import SearchService


def main():
    """Run natural language search tests."""
    print("🔍 Testing Natural Language Search Capabilities\n")

    # Determine database URL
    if os.getenv("USE_TEST_DATABASE") == "true":
        db_url = settings.test_database_url
        print("Using TEST database")
    else:
        db_url = settings.database_url
        print("Using PRODUCTION database")

    # Create session
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Create search service
        search_service = SearchService(db)

        # Test queries
        test_queries = [
            "piano lessons under $50 today",
            "online math tutoring for high school",
            "fitness classes near me",
            "spanish lessons in manhattan",
            "programming tutorials for beginners",
            "yoga classes that are trending",
        ]

        for query in test_queries:
            print(f"\n📝 Query: '{query}'")
            print("-" * 60)

            try:
                # Perform search
                results = search_service.search(query)

                # Display results
                print(f"Found {len(results['services'])} services")

                if results["services"]:
                    print("\nTop results:")
                    for i, service in enumerate(results["services"][:3], 1):
                        print(f"\n{i}. {service['name']} ({service['category']})")
                        if "similarity_score" in service:
                            print(f"   Relevance: {service['similarity_score']:.2%}")
                        if "matching_instructors" in service:
                            print(f"   Available instructors: {service['matching_instructors']}")
                        if "actual_price_range" in service and service["actual_price_range"]["min"]:
                            print(
                                f"   Price range: ${service['actual_price_range']['min']}-${service['actual_price_range']['max']}"
                            )
                        if "analytics" in service and service["analytics"]:
                            analytics = service["analytics"]
                            print(f"   Popularity: {analytics.get('booking_count_30d', 0)} bookings/month")
                            if analytics.get("avg_price_booked"):
                                print(f"   Average price: ${analytics['avg_price_booked']:.2f}")

                # Show parsed query
                if "parsed_query" in results:
                    print(f"\n🧠 Understood as:")
                    parsed = results["parsed_query"]
                    if parsed.get("price_range"):
                        print(
                            f"   - Price: ${parsed['price_range']['min'] or 0}-${parsed['price_range']['max'] or 'any'}"
                        )
                    if parsed.get("location"):
                        print(f"   - Location: {parsed['location']}")
                    if parsed.get("time_constraint"):
                        print(f"   - When: {parsed['time_constraint']}")
                    if parsed.get("modifiers"):
                        print(f"   - Requirements: {', '.join(parsed['modifiers'])}")

            except Exception as e:
                print(f"❌ Error: {str(e)}")

        # Test trending services
        print("\n\n🔥 Trending Services")
        print("-" * 60)

        # Get trending from instructor service
        from app.services.instructor_service import InstructorService

        instructor_service = InstructorService(db)
        trending = instructor_service.get_trending_services(limit=5)

        if trending:
            for i, service in enumerate(trending, 1):
                print(f"{i}. {service['name']}")
                if "analytics" in service:
                    analytics = service["analytics"]
                    print(
                        f"   Search growth: {analytics.get('search_count_7d', 0)*4} → {analytics.get('search_count_30d', 0)}"
                    )
        else:
            print("No trending services found")

    finally:
        db.close()

    print("\n✅ Search test complete!")


if __name__ == "__main__":
    main()
