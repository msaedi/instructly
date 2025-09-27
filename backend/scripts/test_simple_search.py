#!/usr/bin/env python3
"""
Simple test of search functionality.
"""

import os
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.repositories.factory import RepositoryFactory


def main():
    """Run simple search test."""
    print("🔍 Testing Simple Search\n")

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
        # Create repositories
        catalog_repo = RepositoryFactory.create_service_catalog_repository(db)
        analytics_repo = RepositoryFactory.create_service_analytics_repository(db)

        # Test 1: Basic text search
        print("\n1️⃣ Basic Text Search for 'piano'")
        print("-" * 40)
        results = catalog_repo.search_services(query_text="piano", limit=5)
        for service in results:
            print(f"- {service.name} ({service.category.name})")

        # Test 2: Filter by online capability
        print("\n2️⃣ Online Services")
        print("-" * 40)
        results = catalog_repo.search_services(online_capable=True, limit=5)
        for service in results[:5]:
            print(f"- {service.name}")

        # Test 3: Popular services
        print("\n3️⃣ Most Popular Services")
        print("-" * 40)
        popular = catalog_repo.get_popular_services(limit=5, days=30)
        for item in popular:
            service = item["service"]
            analytics = item["analytics"]
            print(f"- {service.name}: {analytics.booking_count_30d} bookings")

        # Test 4: Semantic search
        print("\n4️⃣ Semantic Search Test")
        print("-" * 40)

        # Load model and create embedding
        model = SentenceTransformer("all-MiniLM-L6-v2")
        query = "I want to learn piano"
        embedding = model.encode(query).tolist()

        print(f"Query: '{query}'")
        similar = catalog_repo.find_similar_by_embedding(embedding, limit=5, threshold=0.5)

        if similar:
            print("Similar services:")
            for service, score in similar:
                print(f"- {service.name}: {score:.2%} similarity")
        else:
            print("No similar services found")

        # Test 5: Analytics
        print("\n5️⃣ Service Analytics Sample")
        print("-" * 40)

        # Get a few services with analytics
        services = catalog_repo.find_by(is_active=True)[:5]
        for service in services:
            analytics = analytics_repo.get_or_create(service.id)
            if analytics.booking_count_30d > 0:
                print(f"- {service.name}:")
                print(f"  Bookings: {analytics.booking_count_30d}/month")
                print(f"  Searches: {analytics.search_count_30d}/month")
                if analytics.avg_price_booked:
                    print(f"  Avg Price: ${analytics.avg_price_booked:.2f}")

    finally:
        db.close()

    print("\n✅ Test complete!")


if __name__ == "__main__":
    main()
