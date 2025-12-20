#!/usr/bin/env python3
"""
DEPRECATED: Use generate_openai_embeddings.py instead.

This script used sentence-transformers which has been removed in favor
of OpenAI embeddings for better semantic understanding.

To generate embeddings, run:
    python scripts/generate_openai_embeddings.py

For more information, see the migration notes in:
    docs/temp-logs/nl-search-audit-fixes-and-migration.md
"""

import sys

print("=" * 70)
print("ERROR: This script is deprecated.")
print()
print("The sentence-transformers package has been removed.")
print("Use OpenAI embeddings instead:")
print()
print("    python scripts/generate_openai_embeddings.py")
print()
print("Make sure OPENAI_API_KEY is set in your environment.")
print("=" * 70)
sys.exit(1)

# Original code preserved below for reference (will not execute)
# ----------------------------------------------------------------

import logging
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Note: sentence-transformers import will fail as package was removed
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: sentence-transformers is no longer installed.")
    print("Use: python scripts/generate_openai_embeddings.py")
    sys.exit(1)

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.service_catalog import ServiceCatalog
from app.repositories.factory import RepositoryFactory

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate and store embeddings for service catalog."""

    def __init__(self, db: Session):
        """Initialize with database session and model."""
        self.db = db
        self.catalog_repository = RepositoryFactory.create_service_catalog_repository(db)

        # Load the model - using MiniLM for 384 dimensions
        logger.info("Loading sentence transformer model...")
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Model loaded successfully")

    def generate_service_text(self, service: ServiceCatalog) -> str:
        """
        Generate text representation of a service for embedding.

        Combines name, description, category, and search terms.
        """
        parts = []

        # Add service name (most important)
        parts.append(service.name)

        # Add category name
        if service.category:
            parts.append(f"Category: {service.category.name}")

        # Add description
        if service.description:
            parts.append(service.description)

        # Add search terms
        if service.search_terms:
            parts.append(f"Keywords: {', '.join(service.search_terms)}")

        # Combine all parts
        return " ".join(parts)

    def generate_embeddings(self, batch_size: int = 32) -> int:
        """
        Generate embeddings for all services without embeddings.

        Optimized: sets attributes directly on loaded objects, no per-service SELECT.

        Args:
            batch_size: Number of services to process at once

        Returns:
            Number of services updated
        """
        # Get all active services (already loaded into session)
        services = self.catalog_repository.find_by(is_active=True)

        # Filter services without embeddings
        services_to_update = [s for s in services if s.embedding is None]

        if not services_to_update:
            logger.info("All services already have embeddings")
            return 0

        logger.info(f"Found {len(services_to_update)} services without embeddings")

        # Process in batches - but generate all texts first for efficient encoding
        all_texts = [self.generate_service_text(service) for service in services_to_update]

        # Generate all embeddings at once (most efficient for the model)
        logger.info(f"Generating {len(all_texts)} embeddings in one batch...")
        all_embeddings = self.model.encode(all_texts, convert_to_numpy=True, batch_size=batch_size)

        # Use native bulk UPDATE for performance (1 statement instead of 250)
        # This avoids N round trips to the database
        logger.info(f"Updating {len(services_to_update)} embeddings with bulk UPDATE...")

        # Build list of (id, embedding) tuples
        update_data = []
        for service, embedding in zip(services_to_update, all_embeddings):
            update_data.append({"id": service.id, "embedding": embedding.tolist()})

        # Use psycopg2's execute_values for true batch UPDATE (1 round trip)
        # This is much faster than executemany which does N round trips
        import json  # noqa: PLC0415 - import inside function for performance (only when needed)

        from psycopg2.extras import execute_values

        # Get raw psycopg2 connection
        connection = self.db.connection().connection

        # Build values list: (id, embedding_json_string)
        values = [
            (d["id"], json.dumps(d["embedding"]))
            for d in update_data
        ]

        # Use execute_values with UPDATE ... FROM VALUES pattern
        update_sql = """
            UPDATE service_catalog AS t
            SET embedding = CAST(v.embedding AS vector),
                updated_at = NOW()
            FROM (VALUES %s) AS v(id, embedding)
            WHERE t.id = v.id
        """

        with connection.cursor() as cursor:
            execute_values(cursor, update_sql, values, template="(%s, %s)",
                           page_size=1000)

        self.db.commit()

        updated_count = len(update_data)
        logger.info(f"Committed all {updated_count} embeddings in single bulk UPDATE")

        return updated_count

    def update_embedding(self, service_id: int) -> bool:
        """
        Update embedding for a specific service.

        Args:
            service_id: ID of the service to update

        Returns:
            True if successful, False otherwise
        """
        service = self.catalog_repository.get_by_id(service_id)
        if not service:
            logger.error(f"Service {service_id} not found")
            return False

        # Generate text and embedding
        service_text = self.generate_service_text(service)
        embedding = self.model.encode([service_text], convert_to_numpy=True)[0]

        # Update service
        try:
            self.catalog_repository.update(service.id, embedding=embedding.tolist())
            self.db.commit()
            logger.info(f"Updated embedding for service: {service.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to update service {service.id}: {str(e)}")
            self.db.rollback()
            return False

    def verify_embeddings(self) -> dict:
        """
        Verify that embeddings are properly stored and searchable.

        Returns:
            Dictionary with verification results
        """
        stats = {
            "total_services": 0,
            "services_with_embeddings": 0,
            "services_without_embeddings": 0,
            "embedding_dimensions": 384,
            "sample_searches": [],
        }

        # Get all services
        services = self.catalog_repository.find_by(is_active=True)
        stats["total_services"] = len(services)

        # Count embeddings
        for service in services:
            if service.embedding is not None:
                stats["services_with_embeddings"] += 1
            else:
                stats["services_without_embeddings"] += 1

        # Test a few searches if we have embeddings
        if stats["services_with_embeddings"] > 0:
            test_queries = ["piano lessons for beginners", "math tutoring high school", "yoga fitness online"]

            for query in test_queries:
                # Generate query embedding
                query_embedding = self.model.encode([query], convert_to_numpy=True)[0]

                # Search for similar services
                results = self.catalog_repository.find_similar_by_embedding(
                    embedding=query_embedding.tolist(), limit=3, threshold=0.5
                )

                stats["sample_searches"].append(
                    {"query": query, "results": [{"name": service.name, "score": score} for service, score in results]}
                )

        return stats


def main(skip_verify: bool = False):
    """Main function to generate embeddings.

    Args:
        skip_verify: If True, skip embedding verification (faster for seeding)
    """
    logger.info("Starting embedding generation...")

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
        # Create generator
        generator = EmbeddingGenerator(db)

        # Generate embeddings
        updated_count = generator.generate_embeddings()
        logger.info(f"Successfully generated {updated_count} embeddings")

        # Skip verification if requested (faster for seeding)
        if skip_verify or os.getenv("SKIP_EMBEDDING_VERIFY") == "1":
            logger.info("Skipping embedding verification (--skip-verify or SKIP_EMBEDDING_VERIFY=1)")
            logger.info("\nEmbedding generation complete!")
            return

        # Verify embeddings
        logger.info("Verifying embeddings...")
        stats = generator.verify_embeddings()

        logger.info("Embedding Statistics:")
        logger.info(f"  Total services: {stats['total_services']}")
        logger.info(f"  With embeddings: {stats['services_with_embeddings']}")
        logger.info(f"  Without embeddings: {stats['services_without_embeddings']}")

        if stats["sample_searches"]:
            logger.info("\nSample search results:")
            for search in stats["sample_searches"]:
                logger.info(f"\n  Query: '{search['query']}'")
                for result in search["results"]:
                    logger.info(f"    - {result['name']} (score: {result['score']:.3f})")

        logger.info("\nEmbedding generation complete!")

    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate embeddings for service catalog")
    parser.add_argument("--skip-verify", action="store_true", help="Skip embedding verification")
    args = parser.parse_args()
    main(skip_verify=args.skip_verify)
