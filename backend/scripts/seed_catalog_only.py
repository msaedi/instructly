#!/usr/bin/env python3
"""
Seed service catalog from YAML files.

This script is the SINGLE source of truth for seeding the service catalog.
It can be run standalone or imported by other scripts.

Usage:
    # Standalone:
    python scripts/seed_catalog_only.py

    # With test database:
    USE_TEST_DATABASE=true python scripts/seed_catalog_only.py

    # From another script:
    from seed_catalog_only import seed_catalog
    seed_catalog(db_url="postgresql://...", verbose=True)
"""

import os
from pathlib import Path
import sys
from typing import Dict, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import ulid
import yaml

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.models.service_catalog import ServiceCatalog, ServiceCategory


def load_catalog_yaml() -> Tuple[list, list]:
    """Load catalog data from YAML files."""
    seed_data_dir = Path(__file__).parent / "seed_data" / "catalog"

    # Load categories
    categories_file = seed_data_dir / "categories.yaml"
    with open(categories_file, "r") as f:
        categories_data = yaml.safe_load(f)
        categories = categories_data.get("categories", [])

    # Load services
    services_file = seed_data_dir / "services.yaml"
    with open(services_file, "r") as f:
        services_data = yaml.safe_load(f)
        services = services_data.get("services", [])

    return categories, services


def seed_catalog(db_url: Optional[str] = None, verbose: bool = True) -> Dict[str, int]:
    """
    Seeds service catalog from YAML files.

    Args:
        db_url: Database URL. If None, uses environment configuration
        verbose: Whether to print progress messages

    Returns:
        Dictionary with statistics: {
            'categories_created': int,
            'categories_updated': int,
            'services_created': int,
            'services_updated': int,
            'total_categories': int,
            'total_services': int
        }
    """
    # Determine database URL
    if db_url is None:
        if os.getenv("USE_TEST_DATABASE") == "true":
            db_url = settings.test_database_url
            if verbose:
                print("Using TEST database")
        else:
            db_url = settings.database_url
            if verbose:
                print("Using PRODUCTION database")

    # Create engine and session
    engine = create_engine(db_url)

    # Load YAML data
    categories, services = load_catalog_yaml()

    stats = {
        "categories_created": 0,
        "categories_updated": 0,
        "services_created": 0,
        "services_updated": 0,
        "total_categories": 0,
        "total_services": 0,
    }

    with Session(engine) as session:
        # Use psycopg2's execute_values for true batch operations
        from psycopg2.extras import execute_values
        connection = session.connection().connection

        # Pre-load ALL existing categories by slug in ONE query
        existing_categories = {
            c.slug: c for c in session.query(ServiceCategory).all()
        }
        existing_cat_ids = {c.slug: c.id for c in existing_categories.values()}

        # Build category upsert data
        category_values = []
        for cat_data in categories:
            cat_id = existing_cat_ids.get(cat_data["slug"]) or str(ulid.ULID())
            category_values.append((
                cat_id,
                cat_data["name"],
                cat_data["slug"],
                cat_data.get("subtitle", ""),
                cat_data["description"],
                cat_data["display_order"],
                cat_data.get("icon_name"),
            ))
            if cat_data["slug"] in existing_cat_ids:
                stats["categories_updated"] += 1
            else:
                stats["categories_created"] += 1
            if verbose:
                action = "✓ Updated" if cat_data["slug"] in existing_cat_ids else "+ Created"
                print(f"  {action} category: {cat_data['name']}")

        # Bulk upsert categories (1 round trip)
        category_upsert_sql = """
            INSERT INTO service_categories (id, name, slug, subtitle, description, display_order, icon_name, created_at, updated_at)
            VALUES %s
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                subtitle = EXCLUDED.subtitle,
                description = EXCLUDED.description,
                display_order = EXCLUDED.display_order,
                icon_name = EXCLUDED.icon_name,
                updated_at = NOW()
        """
        with connection.cursor() as cursor:
            execute_values(cursor, category_upsert_sql, category_values,
                           template="(%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
                           page_size=1000)

        stats["total_categories"] = len(categories)

        # Reload categories to get IDs (including newly created)
        session.expire_all()
        all_categories = {c.slug: c for c in session.query(ServiceCategory).all()}
        slug_to_cat_id = {slug: cat.id for slug, cat in all_categories.items()}

        # Pre-load ALL existing services by slug in ONE query
        existing_services = {
            s.slug: s for s in session.query(ServiceCatalog).all()
        }
        existing_svc_ids = {s.slug: s.id for s in existing_services.values()}

        # Build service upsert data
        service_values = []
        slug_to_svc_id = {}  # Track IDs for related_services pass
        for svc_data in services:
            cat_id = slug_to_cat_id.get(svc_data["category_slug"])
            if not cat_id:
                if verbose:
                    print(f"  ⚠ Warning: Category '{svc_data['category_slug']}' not found for service '{svc_data['name']}'")
                continue

            svc_id = existing_svc_ids.get(svc_data["slug"]) or str(ulid.ULID())
            slug_to_svc_id[svc_data["slug"]] = svc_id

            service_values.append((
                svc_id,
                cat_id,
                svc_data["name"],
                svc_data["slug"],
                svc_data["description"],
                svc_data["search_terms"],
                svc_data.get("display_order", 999),
                svc_data.get("online_capable", True),
                svc_data.get("requires_certification", False),
                True,  # is_active
            ))
            if svc_data["slug"] in existing_svc_ids:
                stats["services_updated"] += 1
            else:
                stats["services_created"] += 1
            if verbose:
                action = "✓ Updated" if svc_data["slug"] in existing_svc_ids else "+ Created"
                print(f"  {action} service: {svc_data['name']}")

        # Bulk upsert services (1 round trip)
        service_upsert_sql = """
            INSERT INTO service_catalog (id, category_id, name, slug, description, search_terms, display_order, online_capable, requires_certification, is_active, created_at, updated_at)
            VALUES %s
            ON CONFLICT (slug) DO UPDATE SET
                category_id = EXCLUDED.category_id,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                search_terms = EXCLUDED.search_terms,
                display_order = EXCLUDED.display_order,
                online_capable = EXCLUDED.online_capable,
                requires_certification = EXCLUDED.requires_certification,
                updated_at = NOW()
        """
        with connection.cursor() as cursor:
            execute_values(cursor, service_upsert_sql, service_values,
                           template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
                           page_size=1000)

        stats["total_services"] = len(services)
        session.commit()

        # Second pass: Update related_services (bulk UPDATE)
        # IMPORTANT: Update ALL services to ensure stale relations are cleared
        if verbose:
            print("\n🔗 Updating related services...")

        # Build related_services update data for ALL services
        related_updates = []
        for svc_data in services:
            svc_id = slug_to_svc_id.get(svc_data["slug"])
            if svc_id:
                # Resolve related service slugs to IDs (may be empty list)
                related_ids = [
                    slug_to_svc_id[rs] for rs in svc_data.get("related_services", [])
                    if rs in slug_to_svc_id
                ]
                # Always include - even empty lists to clear stale relations
                related_updates.append((svc_id, related_ids))
                if verbose and related_ids:
                    print(f"  ✓ Updated related services for {svc_data['name']}: {len(related_ids)} connections")

        # Bulk update related_services (1 round trip)
        if related_updates:
            # Re-acquire connection after commit
            connection = session.connection().connection
            related_sql = """
                UPDATE service_catalog
                SET related_services = data.related_services,
                    updated_at = NOW()
                FROM (VALUES %s) AS data(id, related_services)
                WHERE service_catalog.id = data.id
            """
            with connection.cursor() as cursor:
                execute_values(cursor, related_sql, related_updates,
                               template="(%s, %s::text[])",
                               page_size=1000)
            session.commit()

    if verbose:
        print("\n📊 Catalog Seeding Summary:")
        print(
            f"  Categories: {stats['categories_created']} created, {stats['categories_updated']} updated (total: {stats['total_categories']})"
        )
        print(
            f"  Services: {stats['services_created']} created, {stats['services_updated']} updated (total: {stats['total_services']})"
        )

    return stats


def main():
    """CLI interface for standalone usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed service catalog from YAML files")
    parser.add_argument("--db-url", help="Database URL (overrides environment)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    args = parser.parse_args()

    print("🚀 Starting service catalog seeding...")
    stats = seed_catalog(db_url=args.db_url, verbose=not args.quiet)
    print("✅ Service catalog seeding complete!")

    return 0 if stats["total_categories"] > 0 and stats["total_services"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
