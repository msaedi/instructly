#!/usr/bin/env python3
"""
Generate embeddings for service catalog entries.

This script uses sentence-transformers to create semantic embeddings
for all services in the catalog. The embeddings enable natural language
search capabilities.

Usage:
    python scripts/generate_service_embeddings.py
"""

import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from sentence_transformers import SentenceTransformer
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

        Args:
            batch_size: Number of services to process at once

        Returns:
            Number of services updated
        """
        # Get all active services
        services = self.catalog_repository.find_by(is_active=True)

        # Filter services without embeddings
        services_to_update = [s for s in services if s.embedding is None]

        if not services_to_update:
            logger.info("All services already have embeddings")
            return 0

        logger.info(f"Found {len(services_to_update)} services without embeddings")

        # Process in batches
        updated_count = 0
        for i in range(0, len(services_to_update), batch_size):
            batch = services_to_update[i : i + batch_size]

            # Generate text for each service
            texts = [self.generate_service_text(service) for service in batch]

            # Generate embeddings
            logger.info(f"Generating embeddings for batch {i//batch_size + 1}...")
            embeddings = self.model.encode(texts, convert_to_numpy=True)

            # Update services
            for service, embedding in zip(batch, embeddings):
                try:
                    # Update the service with embedding
                    self.catalog_repository.update(service.id, embedding=embedding.tolist())
                    updated_count += 1
                    logger.debug(f"Updated embedding for service: {service.name}")
                except Exception as e:
                    logger.error(f"Failed to update service {service.id}: {str(e)}")

            # Commit batch
            self.db.commit()
            logger.info(f"Committed batch {i//batch_size + 1}")

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
        text = self.generate_service_text(service)
        embedding = self.model.encode([text], convert_to_numpy=True)[0]

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


def main():
    """Main function to generate embeddings."""
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
    main()
