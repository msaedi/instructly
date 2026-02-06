# backend/app/tasks/embedding_migration.py
"""
Background task for maintaining service embeddings.
Run via Celery Beat hourly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from celery.app.task import Task

from app.database import SessionLocal
from app.monitoring.sentry_crons import monitor_if_configured
from app.repositories.service_catalog_repository import ServiceCatalogRepository
from app.services.cache_service import CacheService
from app.services.search.embedding_service import EmbeddingService
from app.tasks.celery_app import typed_task

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 50
MAX_SERVICES_PER_RUN = 200


@typed_task(
    name="maintain_service_embeddings",
    bind=True,
    max_retries=3,
)
@monitor_if_configured("maintain-service-embeddings")
def maintain_service_embeddings(self: "Task[Any, Any]") -> Dict[str, int]:
    """
    Celery task to maintain service embeddings.

    Runs hourly to:
    1. Generate embeddings for new services
    2. Update embeddings for changed services
    3. Re-embed services using outdated model

    Schedule in celery beat:
        'maintain-embeddings': {
            'task': 'maintain_service_embeddings',
            'schedule': crontab(minute=0),  # Every hour
        }
    """
    return asyncio.run(_maintain_embeddings_async())


async def _maintain_embeddings_async() -> Dict[str, int]:
    """Async implementation of embedding maintenance."""
    db = SessionLocal()
    cache = CacheService(db)

    try:
        service = EmbeddingService(cache_service=cache)

        total_updated = 0
        total_failed = 0

        # Process in batches until done or limit reached
        while total_updated + total_failed < MAX_SERVICES_PER_RUN:
            # Get services needing embedding
            services = service.get_services_needing_embedding(db, limit=BATCH_SIZE)

            if not services:
                logger.info("No services need embedding updates")
                break

            logger.info(f"Processing {len(services)} services for embedding")

            # Generate embeddings in batch
            embeddings = await service.embed_services_batch(services, batch_size=BATCH_SIZE)

            # Update each service
            for svc in services:
                if svc.id in embeddings:
                    text = service.generate_embedding_text(svc)
                    text_hash = service.compute_text_hash(text)

                    success = service.update_service_embedding(
                        db,
                        svc.id,
                        embeddings[svc.id],
                        text_hash,
                    )

                    if success:
                        total_updated += 1
                    else:
                        total_failed += 1
                else:
                    total_failed += 1

        # Log summary
        logger.info(
            f"Embedding maintenance complete: {total_updated} updated, {total_failed} failed"
        )

        # Check for alerts
        _check_embedding_coverage(db)

        return {"updated": total_updated, "failed": total_failed}

    except Exception as e:
        logger.error(f"Embedding maintenance failed: {e}")
        raise
    finally:
        db.close()


def _check_embedding_coverage(db: "Session") -> None:
    """Check and alert if too many services lack embeddings."""
    repo = ServiceCatalogRepository(db)

    total = repo.count_active_services()
    missing = repo.count_services_missing_embedding()

    if total > 0:
        missing_pct = (missing / total) * 100

        if missing_pct > 5:
            logger.warning(
                f"HIGH: {missing_pct:.1f}% of services missing embeddings ({missing}/{total})"
            )
        elif missing > 0:
            logger.info(f"LOW: {missing} services missing embeddings ({missing_pct:.1f}%)")
        else:
            logger.info(f"All {total} active services have embeddings")


@typed_task(
    name="bulk_embed_all_services",
    bind=True,
    max_retries=3,
)
def bulk_embed_all_services(self: "Task[Any, Any]") -> Dict[str, int]:
    """
    One-time task to embed all services.

    Run manually for initial migration:
        celery -A app.tasks.celery_app call bulk_embed_all_services
    """
    return asyncio.run(_bulk_embed_async())


async def _bulk_embed_async() -> Dict[str, int]:
    """Bulk embed all services that need it."""
    db = SessionLocal()
    cache = CacheService(db)
    repo = ServiceCatalogRepository(db)

    try:
        service = EmbeddingService(cache_service=cache)

        # Get ALL services needing embedding (no limit)
        services = repo.get_all_services_missing_embedding()

        logger.info(f"Bulk embedding {len(services)} services")

        if not services:
            logger.info("No services need bulk embedding")
            return {"updated": 0, "failed": 0}

        # Process in batches
        total_updated = 0
        total_failed = 0

        for i in range(0, len(services), BATCH_SIZE):
            batch = services[i : i + BATCH_SIZE]
            logger.info(f"Processing batch {i // BATCH_SIZE + 1} ({len(batch)} services)")

            embeddings = await service.embed_services_batch(batch, batch_size=BATCH_SIZE)

            for svc in batch:
                if svc.id in embeddings:
                    text = service.generate_embedding_text(svc)
                    text_hash = service.compute_text_hash(text)

                    success = service.update_service_embedding(
                        db,
                        svc.id,
                        embeddings[svc.id],
                        text_hash,
                    )

                    if success:
                        total_updated += 1
                    else:
                        total_failed += 1
                else:
                    total_failed += 1

        logger.info(f"Bulk embedding complete: {total_updated} updated, {total_failed} failed")

        return {"updated": total_updated, "failed": total_failed}

    except Exception as e:
        logger.error(f"Bulk embedding failed: {e}")
        raise
    finally:
        db.close()
