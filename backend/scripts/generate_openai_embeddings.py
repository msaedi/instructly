#!/usr/bin/env python3
"""
Generate OpenAI embeddings for all services in service_catalog.

Populates the embedding_v2 column (1536 dimensions) using text-embedding-3-small.
This replaces the old sentence-transformers approach.

Usage:
    python scripts/generate_openai_embeddings.py [--batch-size 100] [--force] [--dry-run]

Environment:
    OPENAI_API_KEY - Required
    Uses settings.database_url for database connection
"""

import argparse
import hashlib
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default model - can be overridden via environment
DEFAULT_MODEL = "text-embedding-3-small"


def get_embedding_text(service: Dict[str, Any]) -> str:
    """
    Create searchable text from service data.

    Combines name, description, category, and search terms into
    a single string optimized for embedding.
    """
    parts = []

    # Service name (most important)
    if service.get("name"):
        parts.append(service["name"])

    # Category name
    if service.get("category_name"):
        parts.append(f"Category: {service['category_name']}")

    # Description
    if service.get("description"):
        parts.append(service["description"])

    # Search terms (if available)
    if service.get("search_terms"):
        terms = service["search_terms"]
        if isinstance(terms, list):
            parts.append(f"Keywords: {', '.join(terms)}")

    return " ".join(filter(None, parts))


def compute_text_hash(text: str) -> str:
    """Compute hash of embedding text for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def generate_embeddings(
    batch_size: int = 100,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Generate embeddings for all services using OpenAI API.

    Args:
        batch_size: Number of services to process per API call
        force: If True, regenerate all embeddings even if they exist
        dry_run: If True, only show what would be done
    """
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable required")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_MODEL)

    logger.info(f"Using model: {model}")

    # Connect to database
    db_url = settings.database_url
    logger.info("Connecting to database...")
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Get services that need embeddings
        if force:
            # Regenerate all
            query = text("""
                SELECT
                    sc.id,
                    sc.name,
                    sc.description,
                    sc.search_terms,
                    cat.name as category_name
                FROM service_catalog sc
                LEFT JOIN service_subcategories sub ON sub.id = sc.subcategory_id
                LEFT JOIN service_categories cat ON cat.id = sub.category_id
                WHERE sc.is_active = true
                ORDER BY sc.id
            """)
            logger.info("Force mode: regenerating all embeddings")
        else:
            # Only missing or changed
            query = text("""
                SELECT
                    sc.id,
                    sc.name,
                    sc.description,
                    sc.search_terms,
                    cat.name as category_name
                FROM service_catalog sc
                LEFT JOIN service_subcategories sub ON sub.id = sc.subcategory_id
                LEFT JOIN service_categories cat ON cat.id = sub.category_id
                WHERE sc.is_active = true
                  AND (sc.embedding_v2 IS NULL OR sc.embedding_text_hash IS NULL)
                ORDER BY sc.id
            """)

        result = db.execute(query)
        services = [dict(row._mapping) for row in result]

        if not services:
            logger.info("No services need embedding updates.")
            return

        logger.info(f"Found {len(services)} services to process")

        if dry_run:
            logger.info("DRY RUN - would process these services:")
            for s in services[:10]:
                logger.info(f"  - {s['id']}: {s['name']}")
            if len(services) > 10:
                logger.info(f"  ... and {len(services) - 10} more")
            return

        # Process in batches
        total_processed = 0
        total_tokens = 0

        for i in range(0, len(services), batch_size):
            batch = services[i : i + batch_size]
            texts = [get_embedding_text(s) for s in batch]
            hashes = [compute_text_hash(t) for t in texts]

            batch_num = i // batch_size + 1
            total_batches = (len(services) + batch_size - 1) // batch_size
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} services)...")

            # Call OpenAI API
            try:
                response = client.embeddings.create(
                    model=model,
                    input=texts,
                )

                # Update database
                for j, embedding_data in enumerate(response.data):
                    service = batch[j]
                    embedding = embedding_data.embedding
                    text_hash = hashes[j]

                    update_query = text("""
                        UPDATE service_catalog
                        SET embedding_v2 = :embedding,
                            embedding_model = :model,
                            embedding_text_hash = :text_hash,
                            embedding_updated_at = NOW(),
                            updated_at = NOW()
                        WHERE id = :id
                    """)

                    db.execute(
                        update_query,
                        {
                            "id": service["id"],
                            "embedding": embedding,
                            "model": model,
                            "text_hash": text_hash,
                        },
                    )

                db.commit()
                total_processed += len(batch)
                total_tokens += response.usage.total_tokens

                logger.info(f"  Updated {len(batch)} services ({response.usage.total_tokens} tokens)")

                # Rate limiting - avoid hitting API limits
                if i + batch_size < len(services):
                    time.sleep(0.5)  # Small delay between batches

            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                db.rollback()
                raise

        logger.info(f"\nComplete! Processed {total_processed} services using {total_tokens} tokens")

        # Estimate cost
        cost_per_million = 0.02  # text-embedding-3-small
        estimated_cost = (total_tokens / 1_000_000) * cost_per_million
        logger.info(f"Estimated cost: ${estimated_cost:.4f}")

    finally:
        db.close()


def verify_embeddings() -> Dict[str, Any]:
    """Verify that embeddings are properly stored."""
    db_url = settings.database_url
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Count embeddings
        result = db.execute(
            text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(embedding_v2) as with_embedding,
                    COUNT(*) - COUNT(embedding_v2) as without_embedding
                FROM service_catalog
                WHERE is_active = true
            """)
        )
        row = result.first()

        stats = {
            "total_services": row.total if row else 0,
            "with_embedding": row.with_embedding if row else 0,
            "without_embedding": row.without_embedding if row else 0,
        }

        # Get model distribution
        result = db.execute(
            text("""
                SELECT embedding_model, COUNT(*) as count
                FROM service_catalog
                WHERE is_active = true AND embedding_v2 IS NOT NULL
                GROUP BY embedding_model
            """)
        )
        stats["models"] = {row.embedding_model: row.count for row in result}

        return stats

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Generate OpenAI embeddings for services")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for API calls (default: 100)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate all embeddings even if they exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify embeddings after generation",
    )

    args = parser.parse_args()

    generate_embeddings(
        batch_size=args.batch_size,
        force=args.force,
        dry_run=args.dry_run,
    )

    if args.verify or (not args.dry_run):
        logger.info("\nVerifying embeddings...")
        stats = verify_embeddings()
        logger.info(f"  Total services: {stats['total_services']}")
        logger.info(f"  With embeddings: {stats['with_embedding']}")
        logger.info(f"  Without embeddings: {stats['without_embedding']}")
        if stats.get("models"):
            logger.info(f"  Models used: {stats['models']}")


if __name__ == "__main__":
    main()
