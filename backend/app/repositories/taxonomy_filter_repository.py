# backend/app/repositories/taxonomy_filter_repository.py
"""
Repository for taxonomy filter queries.

Handles all data access for the flexible filter system:
  - Retrieving filters (with valid options) for a subcategory
  - Validating instructor filter selections
  - Finding instructors by JSONB filter_selections
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from sqlalchemy.orm import Session, joinedload

from ..models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from ..models.service_catalog import InstructorService

logger = logging.getLogger(__name__)


class TaxonomyFilterRepository:
    """Repository for taxonomy filter operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Read operations ──────────────────────────────────────────

    def get_filters_for_subcategory(self, subcategory_id: str) -> List[Dict[str, Any]]:
        """Return filters with their valid options for a subcategory.

        Performs the 4-table JOIN:
          subcategory_filters → filter_definitions
          subcategory_filter_options → filter_options

        Returns a list of dicts ready for SubcategoryFilterResponse:
          [
            {
              "filter_key": "grade_level",
              "filter_display_name": "Grade Level",
              "filter_type": "multi_select",
              "options": [
                {"id": "...", "value": "elementary", "display_name": "Elementary (K-5)", "display_order": 0},
                ...
              ]
            },
            ...
          ]
        """
        sub_filters: List[SubcategoryFilter] = (
            self.db.query(SubcategoryFilter)
            .filter(SubcategoryFilter.subcategory_id == subcategory_id)
            .options(
                joinedload(SubcategoryFilter.filter_definition),
                joinedload(SubcategoryFilter.filter_options).joinedload(
                    SubcategoryFilterOption.filter_option
                ),
            )
            .order_by(SubcategoryFilter.display_order)
            .all()
        )

        results: List[Dict[str, Any]] = []
        for sf in sub_filters:
            fd: Optional[FilterDefinition] = sf.filter_definition
            if fd is None:
                continue

            options: List[Dict[str, Any]] = []
            for sfo in sf.filter_options:
                fo: Optional[FilterOption] = sfo.filter_option
                if fo is None:
                    continue
                options.append(
                    {
                        "id": fo.id,
                        "value": fo.value,
                        "display_name": fo.display_name,
                        "display_order": sfo.display_order,
                    }
                )

            results.append(
                {
                    "filter_key": fd.key,
                    "filter_display_name": fd.display_name,
                    "filter_type": fd.filter_type,
                    "options": sorted(options, key=lambda o: o["display_order"]),
                }
            )

        return results

    # ── Validation ───────────────────────────────────────────────

    def validate_filter_selections(
        self,
        subcategory_id: str,
        selections: Dict[str, List[str]],
    ) -> Tuple[bool, List[str]]:
        """Validate that filter selections are legal for a subcategory.

        Checks:
          1. Each key corresponds to a filter assigned to this subcategory.
          2. Each value is an allowed option for that filter+subcategory.

        Returns:
            (is_valid, list_of_error_messages)
        """
        if not selections:
            return True, []

        # Load all subcategory_filters with their options in one query
        sub_filters: List[SubcategoryFilter] = (
            self.db.query(SubcategoryFilter)
            .filter(SubcategoryFilter.subcategory_id == subcategory_id)
            .options(
                joinedload(SubcategoryFilter.filter_definition),
                joinedload(SubcategoryFilter.filter_options).joinedload(
                    SubcategoryFilterOption.filter_option
                ),
            )
            .all()
        )

        # Build lookup: filter_key -> set of valid option values
        valid_map: Dict[str, Set[str]] = {}
        for sf in sub_filters:
            fd = sf.filter_definition
            if fd is None:
                continue
            valid_values: Set[str] = set()
            for sfo in sf.filter_options:
                fo = sfo.filter_option
                if fo is not None:
                    valid_values.add(str(fo.value))
            valid_map[fd.key] = valid_values

        errors: List[str] = []
        for key, values in selections.items():
            if key not in valid_map:
                errors.append(f"Unknown filter key '{key}' for this subcategory")
                continue
            invalid = set(values) - valid_map[key]
            if invalid:
                errors.append(f"Invalid option(s) for '{key}': {sorted(invalid)}")

        return len(errors) == 0, errors

    def get_all_definitions(self, active_only: bool = True) -> List[FilterDefinition]:
        """All filter definitions with their options.

        Useful for admin panels and debug views.

        Args:
            active_only: Only return active definitions.

        Returns:
            List of FilterDefinition with options eagerly loaded.
        """
        query = self.db.query(FilterDefinition).options(joinedload(FilterDefinition.options))

        if active_only:
            query = query.filter(FilterDefinition.is_active.is_(True))

        return cast(
            List[FilterDefinition],
            query.order_by(FilterDefinition.display_order).all(),
        )

    # ── Instructor search by filters ─────────────────────────────

    def find_instructors_by_filters(
        self,
        subcategory_id: str,
        filter_selections: Dict[str, List[str]],
        *,
        active_only: bool = True,
        limit: int = 100,
    ) -> List[InstructorService]:
        """Find instructor_services matching JSONB filter_selections.

        Uses the @> (contains) operator for GIN-indexed queries on
        instructor_services.filter_selections.

        Args:
            subcategory_id: Filter to services in this subcategory.
            filter_selections: Dict of filter_key -> [values] to match.
            active_only: Only return active services.
            limit: Maximum results.

        Returns:
            List of InstructorService rows whose filter_selections
            contain all specified key/value pairs.
        """
        from ..models.service_catalog import ServiceCatalog

        query = (
            self.db.query(InstructorService)
            .join(
                ServiceCatalog,
                InstructorService.service_catalog_id == ServiceCatalog.id,
            )
            .filter(ServiceCatalog.subcategory_id == subcategory_id)
        )

        if active_only:
            query = query.filter(InstructorService.is_active.is_(True))

        # JSONB @> containment — each key/values pair must be present
        if filter_selections:
            query = query.filter(InstructorService.filter_selections.op("@>")(filter_selections))

        return cast(List[InstructorService], query.limit(limit).all())
