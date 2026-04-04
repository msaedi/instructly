"""Shared support and typing base for instructor mixins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    cast,
)

from ..base import BaseService

JsonDict = Dict[str, Any]
JsonList = List[JsonDict]
PRICE_FLOOR_CONFIG_KEYS = {
    "student_location": "private_in_person",
    "instructor_location": "private_in_person",
    "online": "private_remote",
}


@dataclass
class PreparedTeachingLocationGeocode:
    """Async geocoding details prepared for sync profile updates."""

    lat: float | None = None
    lng: float | None = None
    place_id: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


@dataclass
class PreparedProfileUpdateContext:
    """Precomputed async context for profile update work."""

    bio_city: str | None = None
    user_record: Any | None = None
    teaching_location_geocodes: dict[str, PreparedTeachingLocationGeocode] = field(
        default_factory=dict
    )


if TYPE_CHECKING:
    from ..geocoding.base import GeocodingProvider
    from ..instructor_lifecycle_service import InstructorLifecycleService
    from ..location_enrichment import LocationEnrichmentService
    from ..pricing_service import PricingService
    from ..stripe_service import StripeService


class InvalidateOnServiceChangeProtocol(Protocol):
    def __call__(self, service_id: str, change_type: str = "update") -> None:
        ...


class CreateGeocodingProviderProtocol(Protocol):
    def __call__(self, provider_override: Optional[str] = None) -> "GeocodingProvider":
        ...


class InvalidateInstructorProfileChangeProtocol(Protocol):
    def __call__(self, instructor_id: str) -> None:
        ...


class InstructorServiceModuleProtocol(Protocol):
    """Typed surface exposed through the instructor facade lazy import seam."""

    PricingService: ClassVar[type["PricingService"]]
    StripeService: ClassVar[type["StripeService"]]
    InstructorLifecycleService: ClassVar[type["InstructorLifecycleService"]]
    LocationEnrichmentService: ClassVar[type["LocationEnrichmentService"]]
    jitter_coordinates: ClassVar[Callable[..., tuple[float, float]]]
    create_geocoding_provider: ClassVar[CreateGeocodingProviderProtocol]
    invalidate_on_instructor_profile_change: ClassVar[InvalidateInstructorProfileChangeProtocol]
    invalidate_on_service_change: ClassVar[InvalidateOnServiceChangeProtocol]


def get_instructor_service_module() -> InstructorServiceModuleProtocol:
    """Return the instructor facade module for test patch compatibility."""

    from .. import instructor_service as instructor_service_module

    return cast(InstructorServiceModuleProtocol, instructor_service_module)


class InstructorMixinBase(BaseService):
    """Base class used to make instructor mixin dependencies visible to typing."""

    if TYPE_CHECKING:
        from decimal import Decimal

        from ...models.instructor import InstructorPreferredPlace, InstructorProfile
        from ...models.service_catalog import InstructorService as Service, ServiceCatalog
        from ...models.user import User
        from ...repositories.instructor_preferred_place_repository import (
            InstructorPreferredPlaceRepository,
        )
        from ...schemas.instructor import (
            InstructorProfileUpdate,
            PreferredPublicSpaceIn,
            PreferredTeachingLocationIn,
            ServiceCreate,
            UpdateCalendarSettings,
        )
        from ..cache_service import CacheServiceSyncAdapter
        from ..config_service import ConfigService

        cache_service: CacheServiceSyncAdapter | None
        config_service: ConfigService
        profile_repository: Any
        service_repository: Any
        service_format_pricing_repository: Any
        user_repository: Any
        booking_repository: Any
        catalog_repository: Any
        category_repository: Any
        analytics_repository: Any
        preferred_place_repository: InstructorPreferredPlaceRepository
        service_area_repository: Any
        taxonomy_filter_repository: Any

        @staticmethod
        def _extract_profile_basic_updates(update_data: InstructorProfileUpdate) -> dict[str, Any]:
            ...

        def _build_auto_bio(
            self,
            user_id: str,
            services: Sequence[ServiceCreate],
            *,
            user_record: User | None = None,
            city: str | None = None,
        ) -> str:
            ...

        async def _prepare_profile_update_context(
            self, user_id: str, update_data: InstructorProfileUpdate
        ) -> PreparedProfileUpdateContext:
            ...

        def _replace_preferred_places(
            self,
            instructor_id: str,
            kind: str,
            items: Sequence[Any],
            *,
            geocoded_locations: dict[str, PreparedTeachingLocationGeocode] | None = None,
        ) -> None:
            ...

        def _update_services(
            self, profile_id: str, instructor_id: str, services_data: List[ServiceCreate]
        ) -> bool:
            ...

        def _profile_to_dict(
            self,
            profile: InstructorProfile,
            include_inactive_services: bool = False,
        ) -> Dict[str, Any]:
            ...

        def _public_profile_to_dict(
            self,
            profile: InstructorProfile,
            include_inactive_services: bool = False,
        ) -> Dict[str, Any]:
            ...

        def _invalidate_instructor_caches(self, user_id: str) -> None:
            ...

        def get_instructor_profile(
            self, user_id: str, include_inactive_services: bool = False
        ) -> Dict[str, Any]:
            ...

        def get_instructor_teaching_locations(
            self, instructor_id: str
        ) -> List[InstructorPreferredPlace]:
            ...

        def _validate_catalog_ids(self, catalog_ids: List[str]) -> None:
            ...

        @staticmethod
        def _normalize_format_prices(
            format_prices: Sequence[Dict[str, Any]]
        ) -> List[Dict[str, Any]]:
            ...

        def _floor_for_format(self, format_name: str) -> Decimal:
            ...

        @staticmethod
        def _validate_age_groups_subset(
            catalog_service: ServiceCatalog,
            age_groups: Optional[List[str]],
        ) -> None:
            ...

        def validate_service_format_prices(
            self,
            *,
            instructor_id: str,
            catalog_service: ServiceCatalog,
            format_prices: Sequence[Dict[str, Any]],
        ) -> None:
            ...

        def _catalog_service_to_dict(self, service: ServiceCatalog) -> Dict[str, Any]:
            ...

        def _instructor_service_to_dict(self, service: Service) -> Dict[str, Any]:
            ...

        def _get_service_analytics(self, service_catalog_id: str) -> Dict[str, Any]:
            ...

        def _get_instructors_for_service_in_price_range(
            self,
            service_catalog_id: str,
            min_price: Optional[float],
            max_price: Optional[float],
        ) -> List[Any]:
            ...

        def _calculate_price_range(self, instructor_services: List[Any]) -> Dict[str, Any]:
            ...
