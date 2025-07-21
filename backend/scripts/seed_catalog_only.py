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
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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
        # Process categories
        category_map = {}

        for cat_data in categories:
            # Check if category exists
            existing = session.query(ServiceCategory).filter_by(slug=cat_data["slug"]).first()

            if existing:
                # Update existing category
                existing.name = cat_data["name"]
                existing.description = cat_data["description"]
                existing.display_order = cat_data["display_order"]
                category_map[cat_data["slug"]] = existing
                stats["categories_updated"] += 1
                if verbose:
                    print(f"  ✓ Updated category: {cat_data['name']}")
            else:
                # Create new category
                category = ServiceCategory(
                    name=cat_data["name"],
                    slug=cat_data["slug"],
                    description=cat_data["description"],
                    display_order=cat_data["display_order"],
                )
                session.add(category)
                session.flush()
                category_map[cat_data["slug"]] = category
                stats["categories_created"] += 1
                if verbose:
                    print(f"  + Created category: {cat_data['name']}")

        stats["total_categories"] = len(categories)

        # Process services
        for svc_data in services:
            category = category_map.get(svc_data["category_slug"])
            if not category:
                if verbose:
                    print(
                        f"  ⚠ Warning: Category '{svc_data['category_slug']}' not found for service '{svc_data['name']}'"
                    )
                continue

            # Check if service exists
            existing = session.query(ServiceCatalog).filter_by(slug=svc_data["slug"]).first()

            if existing:
                # Update existing service
                existing.category_id = category.id
                existing.name = svc_data["name"]
                existing.description = svc_data["description"]
                existing.search_terms = svc_data["search_terms"]
                existing.typical_duration_options = svc_data["typical_duration_options"]
                existing.min_recommended_price = svc_data["min_recommended_price"]
                existing.max_recommended_price = svc_data["max_recommended_price"]
                stats["services_updated"] += 1
                if verbose:
                    print(f"  ✓ Updated service: {svc_data['name']}")
            else:
                # Create new service
                service = ServiceCatalog(
                    category_id=category.id,
                    name=svc_data["name"],
                    slug=svc_data["slug"],
                    description=svc_data["description"],
                    search_terms=svc_data["search_terms"],
                    typical_duration_options=svc_data["typical_duration_options"],
                    min_recommended_price=svc_data["min_recommended_price"],
                    max_recommended_price=svc_data["max_recommended_price"],
                    is_active=True,
                )
                session.add(service)
                stats["services_created"] += 1
                if verbose:
                    print(f"  + Created service: {svc_data['name']}")

        stats["total_services"] = len(services)

        # Commit all changes
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
