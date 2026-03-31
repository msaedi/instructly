"""Instructor service facade and public re-exports."""

from __future__ import annotations

import os
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models.service_catalog import InstructorService as Service
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from ..repositories.instructor_preferred_place_repository import (
    InstructorPreferredPlaceRepository,
)
from ..utils.location_privacy import jitter_coordinates
from .base import BaseService
from .cache_service import CacheServiceSyncAdapter
from .config_service import ConfigService
from .geocoding.factory import create_geocoding_provider
from .instructor.activation_mixin import InstructorActivationMixin
from .instructor.discovery_mixin import InstructorDiscoveryMixin
from .instructor.location_mixin import InstructorLocationMixin
from .instructor.mixin_base import (
    PreparedProfileUpdateContext,
    PreparedTeachingLocationGeocode,
)
from .instructor.offerings_mixin import InstructorOfferingsMixin
from .instructor.profile_mutations_mixin import InstructorProfileMutationsMixin
from .instructor.profile_reads_mixin import InstructorProfileReadsMixin
from .instructor.taxonomy_reads_mixin import InstructorTaxonomyReadsMixin
from .instructor.validation_helpers_mixin import InstructorValidationHelpersMixin
from .instructor_lifecycle_service import InstructorLifecycleService
from .location_enrichment import LocationEnrichmentService
from .pricing_service import PricingService
from .search.cache_invalidation import (
    invalidate_on_instructor_profile_change,
    invalidate_on_service_change,
)
from .stripe_service import StripeService

__all__ = [
    "InstructorService",
    "PreparedProfileUpdateContext",
    "PreparedTeachingLocationGeocode",
    "get_instructor_service",
    # Legacy compatibility exports kept for tests and patch targets.
    "ConfigService",
    "InstructorLifecycleService",
    "LocationEnrichmentService",
    "PricingService",
    "StripeService",
    "create_geocoding_provider",
    "invalidate_on_instructor_profile_change",
    "invalidate_on_service_change",
    "jitter_coordinates",
]


class InstructorService(
    InstructorProfileReadsMixin,
    InstructorProfileMutationsMixin,
    InstructorLocationMixin,
    InstructorActivationMixin,
    InstructorValidationHelpersMixin,
    InstructorOfferingsMixin,
    InstructorDiscoveryMixin,
    InstructorTaxonomyReadsMixin,
    BaseService,
):
    """Facade class composing instructor service mixins behind the legacy import path."""

    def __init__(
        self,
        db: Session,
        cache_service: Optional[CacheServiceSyncAdapter] = None,
        profile_repository: Optional[Any] = None,
        service_repository: Optional[Any] = None,
        service_format_pricing_repository: Optional[Any] = None,
        user_repository: Optional[Any] = None,
        booking_repository: Optional[Any] = None,
        preferred_place_repository: Optional[InstructorPreferredPlaceRepository] = None,
        config_service: Optional[ConfigService] = None,
    ):
        """Initialize instructor service with database, cache, and repositories."""
        super().__init__(db)
        self.cache_service = cache_service
        self.profile_repository = (
            profile_repository or RepositoryFactory.create_instructor_profile_repository(db)
        )
        self.service_repository = service_repository or RepositoryFactory.create_base_repository(
            db,
            Service,
        )
        self.service_format_pricing_repository = (
            service_format_pricing_repository
            or RepositoryFactory.create_service_format_pricing_repository(db)
        )
        self.user_repository = user_repository or RepositoryFactory.create_base_repository(db, User)
        self.booking_repository = booking_repository or RepositoryFactory.create_booking_repository(
            db
        )
        self.catalog_repository = RepositoryFactory.create_service_catalog_repository(db)
        self.category_repository = RepositoryFactory.create_category_repository(db)
        self.analytics_repository = RepositoryFactory.create_service_analytics_repository(db)
        self.preferred_place_repository = (
            preferred_place_repository
            or RepositoryFactory.create_instructor_preferred_place_repository(db)
        )
        self.service_area_repository = RepositoryFactory.create_instructor_service_area_repository(
            db
        )
        self.taxonomy_filter_repository = RepositoryFactory.create_taxonomy_filter_repository(db)
        self.config_service = config_service or ConfigService(db)
        self._availability_perf_debug = os.getenv("AVAILABILITY_PERF_DEBUG") == "1"


def get_instructor_service(
    db: Session,
    cache_service: Optional[CacheServiceSyncAdapter] = None,
) -> InstructorService:
    """Get instructor service instance for dependency injection."""
    return InstructorService(db, cache_service)
