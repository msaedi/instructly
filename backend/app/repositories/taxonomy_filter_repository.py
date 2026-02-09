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

from sqlalchemy import Text as SAText, cast as sa_cast, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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

    def find_matching_service_ids(
        self,
        service_ids: List[str],
        filter_selections: Dict[str, List[str]],
        *,
        subcategory_id: Optional[str] = None,
        active_only: bool = True,
    ) -> Set[str]:
        """Return candidate instructor_service IDs that satisfy taxonomy filters.

        Semantics:
          - OR within each key: skill_level=beginner,intermediate matches either value.
          - AND across keys: skill_level + goal requires both key-level matches.
        """
        from ..models.service_catalog import ServiceCatalog

        candidate_ids = [str(service_id) for service_id in service_ids if service_id]
        if not candidate_ids:
            return set()

        normalized_filters: Dict[str, List[str]] = {}
        for raw_key, raw_values in (filter_selections or {}).items():
            key = str(raw_key).strip().lower()
            if not key:
                continue

            values: List[str] = []
            seen_values: Set[str] = set()
            for raw_value in raw_values or []:
                value = str(raw_value).strip().lower()
                if not value or value in seen_values:
                    continue
                seen_values.add(value)
                values.append(value)
            if values:
                normalized_filters[key] = values

        base_query = (
            self.db.query(InstructorService.id, InstructorService.filter_selections)
            .join(
                ServiceCatalog,
                InstructorService.service_catalog_id == ServiceCatalog.id,
            )
            .filter(InstructorService.id.in_(candidate_ids))
        )

        if active_only:
            base_query = base_query.filter(InstructorService.is_active.is_(True))
        if subcategory_id:
            base_query = base_query.filter(ServiceCatalog.subcategory_id == subcategory_id)

        dialect_name = (
            self.db.bind.dialect.name.lower()
            if self.db.bind and self.db.bind.dialect and self.db.bind.dialect.name
            else ""
        )
        if dialect_name == "postgresql" and normalized_filters:
            pg_query = base_query
            for key, values in normalized_filters.items():
                json_values_expr = func.coalesce(
                    InstructorService.filter_selections.op("->")(key),
                    sa_cast("[]", JSONB),
                )
                pg_query = pg_query.filter(
                    json_values_expr.op("?|")(sa_cast(values, ARRAY(SAText())))
                )

            rows = pg_query.all()
            return {str(row[0]) for row in rows if row and row[0]}

        # Non-Postgres fallback (or empty filters): evaluate in Python for portability.
        rows = base_query.all()
        if not normalized_filters:
            return {str(row[0]) for row in rows if row and row[0]}

        matching_ids: Set[str] = set()
        for service_id, selections in rows:
            if not service_id:
                continue
            if self._matches_filter_selections(
                selections=selections or {},
                requested=normalized_filters,
            ):
                matching_ids.add(str(service_id))

        return matching_ids

    @staticmethod
    def _matches_filter_selections(
        *,
        selections: Dict[str, Any],
        requested: Dict[str, List[str]],
    ) -> bool:
        """Return True when selections satisfy OR-within-key and AND-across-key rules."""
        for key, requested_values in requested.items():
            raw_values = selections.get(key, [])
            if not isinstance(raw_values, list):
                return False

            candidate_values = {
                str(value).strip().lower() for value in raw_values if str(value).strip()
            }
            requested_set = {
                str(value).strip().lower() for value in requested_values if str(value).strip()
            }

            if requested_set and candidate_values.isdisjoint(requested_set):
                return False

        return True

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
