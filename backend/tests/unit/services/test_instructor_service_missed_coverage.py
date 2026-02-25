"""
Coverage tests for instructor_service.py targeting missed lines and branches.

Targets:
  - L303,309,312,320,331,348: taxonomy filter normalization edge cases
  - L435: catalog service not found during profile creation
  - L789,791: _profile_to_dict with null bio/years
  - L867: update_service_capabilities cache invalidation
  - L907: _update_services catalog not found
  - L1084-1085,1108,1110-1112: geocoding fallback chains in teaching locations
  - L1489: age_groups on create_service
  - L1579: catalog not found in update_filter_selections
  - L2125: get_subcategory_with_services cache hit
  Plus 58 branch parts (if/elif/else chains)
"""

from typing import Any, Optional
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.services.instructor_service import InstructorService


def _make_service() -> InstructorService:
    """Create InstructorService via __new__ with mocked dependencies."""
    svc = InstructorService.__new__(InstructorService)
    svc.db = MagicMock()
    svc.cache_service = None
    svc.profile_repository = MagicMock()
    svc.service_repository = MagicMock()
    svc.user_repository = MagicMock()
    svc.booking_repository = MagicMock()
    svc.catalog_repository = MagicMock()
    svc.category_repository = MagicMock()
    svc.analytics_repository = MagicMock()
    svc.preferred_place_repository = MagicMock()
    svc.service_area_repository = MagicMock()
    svc.taxonomy_filter_repository = MagicMock()
    svc.logger = MagicMock()
    return svc


def _make_mock_profile(
    *,
    user_id: str = "USR_01",
    bio: Optional[str] = "A bio",
    years_experience: Optional[int] = 5,
    services: Optional[list] = None,
    user: Optional[Any] = None,
) -> MagicMock:
    """Create a mock InstructorProfile."""
    profile = MagicMock()
    profile.id = "PROF_01"
    profile.user_id = user_id
    profile.bio = bio
    profile.years_experience = years_experience
    profile.min_advance_booking_hours = 24
    profile.buffer_time_minutes = 15
    profile.skills_configured = True
    profile.identity_verified_at = None
    profile.background_check_uploaded_at = None
    profile.onboarding_completed_at = None
    profile.is_live = False
    profile.is_founding_instructor = False
    profile.created_at = MagicMock()
    profile.updated_at = MagicMock()

    if services is not None:
        profile.services = services
        profile.instructor_services = services
    else:
        profile.services = []
        profile.instructor_services = []

    if user is not None:
        profile.user = user
    else:
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.first_name = "John"
        mock_user.last_name = "Doe"
        mock_user.preferred_places = []
        mock_user.service_areas = []
        profile.user = mock_user

    return profile


@pytest.mark.unit
class TestGetInstructorUser:
    """Cover get_instructor_user branches: no profile, fallback to profile_id lookup."""

    def test_user_found_but_no_profile_raises(self):
        """L161-162: user exists but no instructor profile -> NotFoundException."""
        svc = _make_service()
        mock_user = MagicMock()
        mock_user.id = "USR_01"
        svc.user_repository.get_by_id.return_value = mock_user
        svc.profile_repository.get_by_user_id.return_value = None

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException):
            svc.get_instructor_user("USR_01")

    def test_user_not_found_profile_not_found_raises(self):
        """L166-167: user not found, profile not found -> NotFoundException."""
        svc = _make_service()
        svc.user_repository.get_by_id.return_value = None
        svc.profile_repository.get_by_id.return_value = None

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException):
            svc.get_instructor_user("PROF_01")

    def test_user_not_found_profile_found_but_resolved_user_none(self):
        """L170-171: profile found but resolved user is None -> NotFoundException."""
        svc = _make_service()
        svc.user_repository.get_by_id.side_effect = [None, None]  # First call for user, second for profile.user_id
        mock_profile = MagicMock()
        mock_profile.user_id = "USR_GHOST"
        svc.profile_repository.get_by_id.return_value = mock_profile

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException):
            svc.get_instructor_user("PROF_01")

    def test_user_not_found_profile_found_resolved_user_ok(self):
        """L169-172: profile found, resolved user exists -> returns user."""
        svc = _make_service()
        mock_profile = MagicMock()
        mock_profile.user_id = "USR_RESOLVED"
        resolved_user = MagicMock()
        resolved_user.id = "USR_RESOLVED"

        svc.user_repository.get_by_id.side_effect = [None, resolved_user]
        svc.profile_repository.get_by_id.return_value = mock_profile

        result = svc.get_instructor_user("PROF_01")
        assert result.id == "USR_RESOLVED"


@pytest.mark.unit
class TestProfileToDictBranches:
    """Cover _profile_to_dict with null bio, null years_experience, no user, etc."""

    def test_profile_with_null_bio_and_years(self):
        """L1260-1261: bio=None, years_experience=None."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []
        profile = _make_mock_profile(bio=None, years_experience=None)

        result = svc._profile_to_dict(profile)
        assert result["bio"] is None
        assert result["years_experience"] is None

    def test_profile_with_no_user(self):
        """L1278-1285: profile.user is None -> user field is None."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []
        profile = _make_mock_profile()
        profile.user = None

        # Need to fetch preferred places from repo since user is None
        svc.preferred_place_repository.list_for_instructor.return_value = []

        result = svc._profile_to_dict(profile)
        assert result["user"] is None

    def test_profile_user_no_last_name(self):
        """L1281: user.last_name is empty -> last_initial = ''."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []
        profile = _make_mock_profile()
        profile.user.last_name = ""

        result = svc._profile_to_dict(profile)
        assert result["user"]["last_initial"] == ""

    def test_profile_user_last_name_none(self):
        """L1281: user.last_name is None -> last_initial = ''."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []
        profile = _make_mock_profile()
        profile.user.last_name = None

        result = svc._profile_to_dict(profile)
        assert result["user"]["last_initial"] == ""

    def test_profile_services_source_from_instructor_services(self):
        """L1152-1153: profile.services is None, fallback to instructor_services."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []

        mock_svc = MagicMock()
        mock_svc.id = "SVC_01"
        mock_svc.service_catalog_id = "CAT_01"
        mock_svc.catalog_entry = MagicMock()
        mock_svc.catalog_entry.name = "Piano"
        mock_svc.hourly_rate = 50
        mock_svc.description = "Piano lessons"
        mock_svc.age_groups = ["adults"]
        mock_svc.filter_selections = {}
        mock_svc.equipment_required = None
        mock_svc.offers_travel = False
        mock_svc.offers_at_location = False
        mock_svc.offers_online = True
        mock_svc.duration_options = [60]
        mock_svc.is_active = True

        profile = _make_mock_profile()
        # Simulate profile.services being None
        type(profile).services = PropertyMock(return_value=None)
        profile.instructor_services = [mock_svc]

        result = svc._profile_to_dict(profile)
        assert len(result["services"]) == 1

    def test_profile_services_source_raises_type_error(self):
        """L1156-1157: svcs_source is not iterable -> services = []."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []

        profile = _make_mock_profile()
        type(profile).services = PropertyMock(return_value=None)
        profile.instructor_services = 42  # Not iterable

        result = svc._profile_to_dict(profile)
        assert result["services"] == []

    def test_profile_include_inactive_services(self):
        """L1159-1160: include_inactive_services=True keeps all services."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []

        active_svc = MagicMock()
        active_svc.is_active = True
        active_svc.id = "SVC_01"
        active_svc.service_catalog_id = "CAT_01"
        active_svc.catalog_entry = MagicMock()
        active_svc.catalog_entry.name = "Piano"
        active_svc.hourly_rate = 50
        active_svc.description = "Piano"
        active_svc.age_groups = []
        active_svc.filter_selections = {}
        active_svc.equipment_required = None
        active_svc.offers_travel = False
        active_svc.offers_at_location = False
        active_svc.offers_online = True
        active_svc.duration_options = [60]

        inactive_svc = MagicMock()
        inactive_svc.is_active = False
        inactive_svc.id = "SVC_02"
        inactive_svc.service_catalog_id = "CAT_02"
        inactive_svc.catalog_entry = MagicMock()
        inactive_svc.catalog_entry.name = "Guitar"
        inactive_svc.hourly_rate = 45
        inactive_svc.description = "Guitar"
        inactive_svc.age_groups = []
        inactive_svc.filter_selections = {}
        inactive_svc.equipment_required = None
        inactive_svc.offers_travel = False
        inactive_svc.offers_at_location = False
        inactive_svc.offers_online = True
        inactive_svc.duration_options = [60]

        profile = _make_mock_profile(services=[active_svc, inactive_svc])

        result_active_only = svc._profile_to_dict(profile, include_inactive_services=False)
        assert len(result_active_only["services"]) == 1

        result_all = svc._profile_to_dict(profile, include_inactive_services=True)
        assert len(result_all["services"]) == 2


@pytest.mark.unit
class TestProfileToDictPreferredPlaces:
    """Cover preferred places loading branches."""

    def test_preferred_places_from_user_attribute(self):
        """L1163-1168: user has preferred_places -> uses them directly."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []

        place = MagicMock()
        place.kind = "teaching_location"
        place.position = 0
        place.address = "123 Main St"
        place.label = "Home"
        place.approx_lat = 40.75
        place.approx_lng = -73.99
        place.neighborhood = "Midtown"

        profile = _make_mock_profile()
        profile.user.preferred_places = [place]

        result = svc._profile_to_dict(profile)
        assert len(result["preferred_teaching_locations"]) == 1
        assert result["preferred_teaching_locations"][0]["neighborhood"] == "Midtown"

    def test_preferred_places_not_iterable(self):
        """L1167-1168: user.preferred_places not iterable -> fallback to repo."""
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []
        svc.preferred_place_repository.list_for_instructor.return_value = []

        profile = _make_mock_profile()
        profile.user.preferred_places = 42  # Not iterable

        result = svc._profile_to_dict(profile)
        assert result["preferred_teaching_locations"] == []


@pytest.mark.unit
class TestProfileToDictServiceAreas:
    """Cover service area processing branches."""

    def test_multiple_boroughs_summary(self):
        """L1252-1253: >2 boroughs -> 'X + N more'."""
        svc = _make_service()

        area1 = MagicMock()
        area1.neighborhood_id = "N1"
        area1.is_active = True
        region1 = MagicMock()
        region1.region_code = "MN01"
        region1.region_name = "Midtown"
        region1.parent_region = "Manhattan"
        region1.region_metadata = None
        area1.neighborhood = region1

        area2 = MagicMock()
        area2.neighborhood_id = "N2"
        area2.is_active = True
        region2 = MagicMock()
        region2.region_code = "BK01"
        region2.region_name = "Park Slope"
        region2.parent_region = "Brooklyn"
        region2.region_metadata = None
        area2.neighborhood = region2

        area3 = MagicMock()
        area3.neighborhood_id = "N3"
        area3.is_active = True
        region3 = MagicMock()
        region3.region_code = "QN01"
        region3.region_name = "Astoria"
        region3.parent_region = "Queens"
        region3.region_metadata = None
        area3.neighborhood = region3

        profile = _make_mock_profile()
        profile.user.service_areas = [area1, area2, area3]

        result = svc._profile_to_dict(profile)
        assert "+ 2 more" in result["service_area_summary"]

    def test_region_metadata_fallback(self):
        """L1229-1234: region_metadata provides nta_code, nta_name, borough."""
        svc = _make_service()

        area = MagicMock()
        area.neighborhood_id = "N1"
        area.is_active = True
        region = MagicMock()
        region.region_code = None
        region.region_name = None
        region.parent_region = None
        region.region_metadata = {
            "nta_code": "MN99",
            "nta_name": "Chelsea",
            "borough": "Manhattan",
        }
        area.neighborhood = region

        profile = _make_mock_profile()
        profile.user.service_areas = [area]

        result = svc._profile_to_dict(profile)
        assert result["service_area_neighborhoods"][0]["ntacode"] == "MN99"
        assert result["service_area_neighborhoods"][0]["name"] == "Chelsea"
        assert result["service_area_neighborhoods"][0]["borough"] == "Manhattan"

    def test_no_region_on_area(self):
        """L1222-1228: area.neighborhood is None -> no region metadata."""
        svc = _make_service()

        area = MagicMock()
        area.neighborhood_id = "N1"
        area.is_active = True
        area.neighborhood = None

        profile = _make_mock_profile()
        profile.user.service_areas = [area]

        result = svc._profile_to_dict(profile)
        assert result["service_area_neighborhoods"][0]["ntacode"] is None


@pytest.mark.unit
class TestCreateInstructorProfileBranches:
    """Cover create_instructor_profile error paths."""

    def test_catalog_service_not_found_during_creation(self):
        """L434-435: catalog_service not found -> NotFoundException."""
        svc = _make_service()
        svc.profile_repository.exists.return_value = False

        mock_profile = MagicMock()
        mock_profile.id = "PROF_01"
        svc.profile_repository.create.return_value = mock_profile

        # Mock service_data
        mock_service_data = MagicMock()
        mock_service_data.service_catalog_id = "CAT_MISSING"
        mock_service_data.model_dump.return_value = {
            "service_catalog_id": "CAT_MISSING",
            "hourly_rate": 50,
        }

        mock_profile_data = MagicMock()
        mock_profile_data.services = [mock_service_data]
        mock_profile_data.model_dump.return_value = {"bio": "test"}

        svc.catalog_repository.get_by_id.return_value = None

        # transaction context manager
        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        mock_user = MagicMock()
        mock_user.id = "USR_01"

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException, match="Catalog service not found"):
            svc.create_instructor_profile(mock_user, mock_profile_data)


@pytest.mark.unit
class TestTeachingLocationGeocoding:
    """Cover geocoding fallback chains in _replace_preferred_places."""

    def _make_place_item(self, address="123 Main St", label="Home"):
        """Create a mock PreferredTeachingLocationIn."""
        item = MagicMock()
        item.address = address
        item.label = label
        return item

    def test_geocoding_city_only_neighborhood(self):
        """L1084: city without state -> neighborhood = city."""
        svc = _make_service()

        # No existing places
        svc.preferred_place_repository.list_for_instructor_and_kind.return_value = []
        svc.preferred_place_repository.delete_for_kind = MagicMock()
        svc.preferred_place_repository.flush = MagicMock()
        svc.preferred_place_repository.create_for_kind = MagicMock()
        svc.db.expire_all = MagicMock()

        mock_geocoded = MagicMock()
        mock_geocoded.latitude = 40.75
        mock_geocoded.longitude = -73.99
        mock_geocoded.provider_id = None
        mock_geocoded.neighborhood = None
        mock_geocoded.city = "New York"
        mock_geocoded.state = None

        with patch("app.services.instructor_service.create_geocoding_provider") as mock_geo_factory:
            mock_provider = MagicMock()
            mock_geo_factory.return_value = mock_provider

            with patch("app.services.instructor_service.anyio") as mock_anyio:
                mock_anyio.run.return_value = mock_geocoded

                with patch("app.services.instructor_service.jitter_coordinates", return_value=(40.751, -73.991)):
                    with patch("app.services.instructor_service.LocationEnrichmentService") as mock_enrich_cls:
                        mock_enricher = MagicMock()
                        mock_enricher.enrich.return_value = {"neighborhood": None, "district": None}
                        mock_enrich_cls.return_value = mock_enricher

                        item = self._make_place_item()
                        svc._replace_preferred_places("USR_01", "teaching_location", [item])

                        svc.preferred_place_repository.create_for_kind.assert_called_once()
                        call_kwargs = svc.preferred_place_repository.create_for_kind.call_args
                        assert call_kwargs.kwargs.get("neighborhood") == "New York"

    def test_geocoding_failure_logs_debug(self):
        """L1086-1091: geocoding exception is caught and logged."""
        svc = _make_service()

        svc.preferred_place_repository.list_for_instructor_and_kind.return_value = []
        svc.preferred_place_repository.delete_for_kind = MagicMock()
        svc.preferred_place_repository.flush = MagicMock()
        svc.preferred_place_repository.create_for_kind = MagicMock()
        svc.db.expire_all = MagicMock()

        with patch("app.services.instructor_service.create_geocoding_provider") as mock_geo_factory:
            mock_provider = MagicMock()
            mock_geo_factory.return_value = mock_provider

            with patch("app.services.instructor_service.anyio") as mock_anyio:
                mock_anyio.run.side_effect = Exception("Geocoding failed")

                item = self._make_place_item()
                # Should not raise
                svc._replace_preferred_places("USR_01", "teaching_location", [item])
                svc.preferred_place_repository.create_for_kind.assert_called_once()

    def test_enrichment_district_without_neighborhood(self):
        """L1107-1108: enrichment has district but no neighborhood -> neighborhood = district."""
        svc = _make_service()

        svc.preferred_place_repository.list_for_instructor_and_kind.return_value = []
        svc.preferred_place_repository.delete_for_kind = MagicMock()
        svc.preferred_place_repository.flush = MagicMock()
        svc.preferred_place_repository.create_for_kind = MagicMock()
        svc.db.expire_all = MagicMock()

        mock_geocoded = MagicMock()
        mock_geocoded.latitude = 40.75
        mock_geocoded.longitude = -73.99
        mock_geocoded.provider_id = None
        mock_geocoded.neighborhood = None
        mock_geocoded.city = None
        mock_geocoded.state = None

        with patch("app.services.instructor_service.create_geocoding_provider") as mock_geo_factory:
            mock_provider = MagicMock()
            mock_geo_factory.return_value = mock_provider

            with patch("app.services.instructor_service.anyio") as mock_anyio:
                mock_anyio.run.return_value = mock_geocoded

                with patch("app.services.instructor_service.jitter_coordinates", return_value=(40.751, -73.991)):
                    with patch("app.services.instructor_service.LocationEnrichmentService") as mock_enrich_cls:
                        mock_enricher = MagicMock()
                        mock_enricher.enrich.return_value = {
                            "neighborhood": None,
                            "district": "Manhattan",
                        }
                        mock_enrich_cls.return_value = mock_enricher

                        item = self._make_place_item()
                        svc._replace_preferred_places("USR_01", "teaching_location", [item])

                        call_kwargs = svc.preferred_place_repository.create_for_kind.call_args
                        assert call_kwargs.kwargs.get("neighborhood") == "Manhattan"

    def test_enrichment_exception_swallowed(self):
        """L1111-1115: LocationEnrichmentService raises -> caught silently."""
        svc = _make_service()

        svc.preferred_place_repository.list_for_instructor_and_kind.return_value = []
        svc.preferred_place_repository.delete_for_kind = MagicMock()
        svc.preferred_place_repository.flush = MagicMock()
        svc.preferred_place_repository.create_for_kind = MagicMock()
        svc.db.expire_all = MagicMock()

        mock_geocoded = MagicMock()
        mock_geocoded.latitude = 40.75
        mock_geocoded.longitude = -73.99
        mock_geocoded.provider_id = None
        mock_geocoded.neighborhood = None
        mock_geocoded.city = None
        mock_geocoded.state = None

        with patch("app.services.instructor_service.create_geocoding_provider") as mock_geo_factory:
            mock_provider = MagicMock()
            mock_geo_factory.return_value = mock_provider

            with patch("app.services.instructor_service.anyio") as mock_anyio:
                mock_anyio.run.return_value = mock_geocoded

                with patch("app.services.instructor_service.jitter_coordinates", return_value=(40.751, -73.991)):
                    with patch("app.services.instructor_service.LocationEnrichmentService") as mock_enrich_cls:
                        mock_enricher = MagicMock()
                        mock_enricher.enrich.side_effect = Exception("Enrichment error")
                        mock_enrich_cls.return_value = mock_enricher

                        item = self._make_place_item()
                        # Should not raise
                        svc._replace_preferred_places("USR_01", "teaching_location", [item])
                        svc.preferred_place_repository.create_for_kind.assert_called_once()


@pytest.mark.unit
class TestNormalizeTaxonomyFilters:
    """Cover taxonomy filter normalization in get_instructors_filtered."""

    def test_empty_filter_key_skipped(self):
        """L302: empty key after strip -> skipped."""
        svc = _make_service()

        svc.profile_repository.find_by_filters.return_value = []

        result = svc.get_instructors_filtered(taxonomy_filter_selections={"  ": ["val"]})
        assert result["instructors"] == []

    def test_empty_filter_value_skipped(self):
        """L308: empty value after strip -> skipped."""
        svc = _make_service()

        svc.profile_repository.find_by_filters.return_value = []

        result = svc.get_instructors_filtered(taxonomy_filter_selections={"key": ["", "  "]})
        assert result["instructors"] == []

    def test_duplicate_filter_values_deduped(self):
        """L308-309: duplicate values -> only unique kept."""
        svc = _make_service()

        svc.profile_repository.find_by_filters.return_value = []

        result = svc.get_instructors_filtered(taxonomy_filter_selections={"key": ["val", "val"]})
        assert result["instructors"] == []


@pytest.mark.unit
class TestCacheInvalidation:
    """Cover cache invalidation branch when cache_service is set."""

    def test_update_service_capabilities_with_cache(self):
        """L867-869: cache_service is set -> _invalidate_instructor_caches called."""
        svc = _make_service()
        svc.cache_service = MagicMock()

        mock_service = MagicMock()
        mock_service.id = "SVC_01"
        mock_service.instructor_profile = MagicMock()
        mock_service.instructor_profile.user_id = "USR_01"
        mock_service.offers_travel = False
        mock_service.offers_at_location = False
        mock_service.offers_online = True
        mock_service.catalog_entry = MagicMock()
        mock_service.catalog_entry.name = "Piano"
        mock_service.catalog_entry.description = "Piano lessons"
        mock_service.service_catalog_id = "CAT_01"
        mock_service.hourly_rate = 50
        mock_service.description = "Piano"
        mock_service.filter_selections = {}
        mock_service.duration_options = [60]
        mock_service.is_active = True
        mock_service.created_at = None
        mock_service.updated_at = None
        mock_service.category = "Music"

        svc.service_repository.get_by_id.return_value = mock_service
        svc.service_area_repository.list_for_instructor.return_value = []

        # Mock transaction
        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.services.instructor_service.invalidate_on_service_change"):
            svc.update_service_capabilities(
                "SVC_01", "USR_01", {"offers_online": True}
            )

        svc.cache_service.delete.assert_called()


@pytest.mark.unit
class TestGetSubcategoryWithServicesCache:
    """Cover get_subcategory_with_services cache hit path."""

    def test_cache_hit_returns_cached(self):
        """L2124-2125: cache hit -> returns cached value."""
        svc = _make_service()
        svc.cache_service = MagicMock()
        cached_data = {"id": "SUB_01", "name": "Test", "services": []}
        svc.cache_service.get.return_value = cached_data

        result = svc.get_subcategory_with_services("SUB_01")
        assert result == cached_data

    def test_cache_miss_fetches_from_repo(self):
        """L2127-2143: cache miss -> fetches from repo and caches."""
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        mock_sub = MagicMock()
        mock_sub.id = "SUB_01"
        mock_sub.name = "Test Sub"
        mock_sub.category_id = "CAT_01"
        mock_sub.display_order = 1
        mock_sub.services = []

        svc.catalog_repository.get_subcategory_with_services.return_value = mock_sub

        result = svc.get_subcategory_with_services("SUB_01")
        assert result["name"] == "Test Sub"
        svc.cache_service.set.assert_called_once()

    def test_subcategory_not_found_raises(self):
        """L2128-2129: subcategory not found -> NotFoundException."""
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_subcategory_with_services.return_value = None

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException):
            svc.get_subcategory_with_services("SUB_MISSING")


@pytest.mark.unit
class TestCreateServiceAgeGroups:
    """Cover create_instructor_service_from_catalog with age_groups kwarg."""

    def test_create_service_with_age_groups(self):
        """L1488-1489: age_groups provided -> included in create_kwargs."""
        svc = _make_service()
        svc.cache_service = None

        mock_profile = MagicMock()
        mock_profile.id = "PROF_01"
        svc.profile_repository.find_one_by.return_value = mock_profile

        mock_catalog = MagicMock()
        mock_catalog.id = "CAT_01"
        mock_catalog.name = "Piano"
        mock_catalog.subcategory_id = "SUB_01"
        mock_catalog.eligible_age_groups = ["kids", "adults"]
        svc.catalog_repository.get_by_id.return_value = mock_catalog

        svc.service_repository.find_one_by.return_value = None  # No existing

        mock_created = MagicMock()
        mock_created.id = "SVC_01"
        mock_created.service_catalog_id = "CAT_01"
        mock_created.catalog_entry = mock_catalog
        mock_created.hourly_rate = 50
        mock_created.description = "Piano"
        mock_created.filter_selections = {}
        mock_created.duration_options = [60]
        mock_created.offers_travel = False
        mock_created.offers_at_location = False
        mock_created.offers_online = True
        mock_created.is_active = True
        mock_created.created_at = None
        mock_created.updated_at = None
        mock_created.category = "Music"
        svc.service_repository.create.return_value = mock_created

        # Mock transaction
        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.services.instructor_service.invalidate_on_service_change"):
            svc.create_instructor_service_from_catalog(
                instructor_id="USR_01",
                catalog_service_id="CAT_01",
                hourly_rate=50,
                age_groups=["kids"],
            )

        # Verify age_groups was passed to create
        create_call = svc.service_repository.create.call_args
        assert "age_groups" in create_call.kwargs


# ── Additional coverage: branches still uncovered ────────────────


@pytest.mark.unit
class TestCreateInstructorProfileNoServices:
    """Covers 419->424 (no services) and 440->444 (empty services_data list)."""

    def test_no_services_skips_validation_and_bulk_create(self):
        """When profile_data.services is empty list, skip catalog validation + bulk_create."""
        svc = _make_service()
        svc.profile_repository.exists.return_value = False
        profile = MagicMock()
        profile.id = "PROF_01"
        svc.profile_repository.create.return_value = profile
        user = MagicMock()
        user.id = "USR_01"
        svc.user_repository.get_by_id.return_value = user

        # Use a mock to bypass schema validation for the empty-services edge case
        data = MagicMock()
        data.services = []  # Empty services list
        data.model_dump.return_value = {"bio": "Experienced instructor with many skills."}

        with patch("app.services.permission_service.PermissionService"):
            with patch.object(svc, "_profile_to_dict", return_value={"id": "PROF_01"}):
                result = svc.create_instructor_profile(user, data)

        assert result == {"id": "PROF_01"}
        svc.service_repository.bulk_create.assert_not_called()


@pytest.mark.unit
class TestGetPublicInstructorProfileCacheBranches:
    """Covers 463->469 (cache hit/miss) and 476->480 (cache set/skip)."""

    def test_cache_hit_returns_cached_value(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = {"id": "cached"}
        result = svc.get_public_instructor_profile("INST_01")
        assert result == {"id": "cached"}
        svc.profile_repository.get_public_by_id.assert_not_called()

    def test_no_cache_service_profile_not_found(self):
        """463->469 branch: no cache_service => skip cache, profile None => return None."""
        svc = _make_service()
        svc.cache_service = None
        svc.profile_repository.get_public_by_id.return_value = None
        result = svc.get_public_instructor_profile("INST_01")
        assert result is None

    def test_cache_miss_stores_and_returns(self):
        """476->480 branch: cache service exists, cache miss, stores result."""
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.profile_repository.get_public_by_id.return_value = MagicMock()
        with patch.object(svc, "_profile_to_dict", return_value={"id": "p-1"}):
            result = svc.get_public_instructor_profile("INST_01")
        assert result == {"id": "p-1"}
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service_profile_found_skips_cache_set(self):
        """476->480 branch: no cache_service => don't call set."""
        svc = _make_service()
        svc.cache_service = None
        svc.profile_repository.get_public_by_id.return_value = MagicMock()
        with patch.object(svc, "_profile_to_dict", return_value={"id": "p-1"}):
            result = svc.get_public_instructor_profile("INST_01")
        assert result == {"id": "p-1"}


@pytest.mark.unit
class TestUpdateProfileAutoBioZipAndCatalog:
    """Covers 522->530, 525->530, 536->532 (auto-bio geocoding branches)."""

    def _setup(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc._invalidate_instructor_caches = MagicMock()
        svc._update_services = MagicMock(return_value=False)
        svc.get_instructor_profile = MagicMock(return_value={"id": "p-1"})
        profile = MagicMock()
        profile.id = "PROF_01"
        profile.user_id = "USR_01"
        profile.bio = None
        profile.years_experience = 3
        svc.profile_repository.find_one_by.return_value = profile
        svc.profile_repository.update.return_value = profile
        return svc

    def test_user_no_zip_code_default_city(self):
        """522->530: user has no zip_code => skip geocoding => city = 'New York'."""
        from types import SimpleNamespace

        from app.schemas.instructor import ServiceCreate

        svc = self._setup()
        svc.user_repository.get_by_id.return_value = SimpleNamespace(
            first_name="Dana", zip_code=None
        )
        svc.catalog_repository.get_by_id.return_value = SimpleNamespace(name="Piano")

        sc = ServiceCreate(
            offers_travel=False, offers_at_location=False, offers_online=True,
            service_catalog_id="cat-1", hourly_rate=60.0, description="L", duration_options=[60],
        )
        update_data = MagicMock()
        update_data.model_dump.return_value = {}
        update_data.services = [sc]
        update_data.preferred_teaching_locations = None
        update_data.preferred_public_spaces = None

        with patch("app.services.instructor_service.InstructorLifecycleService"):
            with patch("app.services.instructor_service.invalidate_on_instructor_profile_change"):
                svc.update_instructor_profile("USR_01", update_data)

        _, kwargs = svc.profile_repository.update.call_args
        assert "New York" in kwargs["bio"]

    def test_geocoded_returns_none_city(self):
        """525->530: geocoded has city=None => city stays 'New York'."""
        from types import SimpleNamespace
        from unittest.mock import Mock

        from app.schemas.instructor import ServiceCreate

        svc = self._setup()
        svc.user_repository.get_by_id.return_value = SimpleNamespace(
            first_name="Sam", zip_code="10001"
        )
        svc.catalog_repository.get_by_id.return_value = SimpleNamespace(name="Chess")

        sc = ServiceCreate(
            offers_travel=False, offers_at_location=False, offers_online=True,
            service_catalog_id="cat-1", hourly_rate=60.0, description="L", duration_options=[60],
        )
        update_data = MagicMock()
        update_data.model_dump.return_value = {}
        update_data.services = [sc]
        update_data.preferred_teaching_locations = None
        update_data.preferred_public_spaces = None

        with patch("app.services.instructor_service.create_geocoding_provider") as gp:
            gp.return_value = SimpleNamespace(geocode=Mock())
            with patch("app.services.instructor_service.anyio.run") as arun:
                arun.return_value = SimpleNamespace(city=None)
                with patch("app.services.instructor_service.InstructorLifecycleService"):
                    with patch("app.services.instructor_service.invalidate_on_instructor_profile_change"):
                        svc.update_instructor_profile("USR_01", update_data)

        _, kwargs = svc.profile_repository.update.call_args
        assert "New York" in kwargs["bio"]

    def test_catalog_entry_no_name_skipped(self):
        """536->532: catalog_entry.name is None => skill skipped."""
        from types import SimpleNamespace

        from app.schemas.instructor import ServiceCreate

        svc = self._setup()
        svc.user_repository.get_by_id.return_value = SimpleNamespace(
            first_name="Lee", zip_code=None
        )
        svc.catalog_repository.get_by_id.side_effect = [
            SimpleNamespace(name=None),
            SimpleNamespace(name="Yoga"),
        ]

        sc1 = ServiceCreate(
            offers_travel=False, offers_at_location=False, offers_online=True,
            service_catalog_id="cat-1", hourly_rate=60.0, description="L", duration_options=[60],
        )
        sc2 = ServiceCreate(
            offers_travel=False, offers_at_location=False, offers_online=True,
            service_catalog_id="cat-2", hourly_rate=60.0, description="L", duration_options=[60],
        )
        update_data = MagicMock()
        update_data.model_dump.return_value = {}
        update_data.services = [sc1, sc2]
        update_data.preferred_teaching_locations = None
        update_data.preferred_public_spaces = None

        with patch("app.services.instructor_service.InstructorLifecycleService"):
            with patch("app.services.instructor_service.invalidate_on_instructor_profile_change"):
                svc.update_instructor_profile("USR_01", update_data)

        _, kwargs = svc.profile_repository.update.call_args
        assert "yoga" in kwargs["bio"]


@pytest.mark.unit
class TestUpdateServiceCapabilitiesMissed:
    """Covers line 789 (service not found) and 867->869 no-cache branch."""

    def test_service_not_found(self):
        svc = _make_service()
        svc.service_repository.get_by_id.return_value = None
        from app.core.exceptions import NotFoundException

        with pytest.raises(NotFoundException):
            svc.update_service_capabilities("SVC_X", "USR_01", {})

    def test_no_cache_service_skips_invalidation(self):
        svc = _make_service()
        svc.cache_service = None
        mock_service = MagicMock()
        mock_service.instructor_profile.user_id = "USR_01"
        mock_service.offers_online = True
        svc.service_repository.get_by_id.return_value = mock_service

        with patch.object(svc, "validate_service_capabilities"):
            with patch.object(svc, "_instructor_service_to_dict", return_value={}):
                with patch("app.services.instructor_service.invalidate_on_service_change"):
                    svc.update_service_capabilities("SVC_01", "USR_01", {})


@pytest.mark.unit
class TestUpdateServicesCatalogMissing:
    """Covers line 907 — catalog_svc None in _update_services loop."""

    def test_catalog_not_found_raises_not_found(self):
        svc = _make_service()
        svc.catalog_repository.exists.return_value = True
        svc.service_repository.find_by.return_value = []
        svc.catalog_repository.get_by_id.return_value = None

        from app.core.exceptions import NotFoundException
        from app.schemas.instructor import ServiceCreate

        sc = ServiceCreate(
            offers_travel=False, offers_at_location=False, offers_online=True,
            service_catalog_id="cat-1", hourly_rate=60.0, description="L", duration_options=[60],
        )
        with pytest.raises(NotFoundException, match="Catalog service not found"):
            svc._update_services("p-1", "u-1", [sc])


@pytest.mark.unit
class TestReplacePreferredPlacesMissedBranches:
    """Covers 1010->1021 (empty teaching location items with/without at_location services),
    1189->1191 (place.label falsy)."""

    def test_teaching_location_empty_items_no_at_location_ok(self):
        """1010->1021: profile has services but none offer at_location."""
        svc = _make_service()
        profile = MagicMock()
        profile.id = "p-1"
        svc.profile_repository.get_by_user_id.return_value = profile
        mock_svc = MagicMock()
        mock_svc.offers_at_location = False
        svc.service_repository.find_by.return_value = [mock_svc]
        svc.preferred_place_repository.list_for_instructor_and_kind.return_value = []

        svc._replace_preferred_places("USR_01", "teaching_location", [])
        svc.preferred_place_repository.delete_for_kind.assert_called_once()

    def test_teaching_location_empty_items_with_at_location_raises(self):
        """1010->1021: service offers at_location => BusinessRuleException."""
        from app.core.exceptions import BusinessRuleException

        svc = _make_service()
        profile = MagicMock()
        profile.id = "p-1"
        svc.profile_repository.get_by_user_id.return_value = profile
        mock_svc = MagicMock()
        mock_svc.offers_at_location = True
        svc.service_repository.find_by.return_value = [mock_svc]
        svc.preferred_place_repository.list_for_instructor_and_kind.return_value = []

        with pytest.raises(BusinessRuleException, match="teaching location"):
            svc._replace_preferred_places("USR_01", "teaching_location", [])

    def test_public_space_skips_geocoding(self):
        """Public space kind doesn't gather existing places or geocode."""
        svc = _make_service()
        item = MagicMock()
        item.address = "Central Park"
        item.label = None
        svc._replace_preferred_places("USR_01", "public_space", [item])
        svc.preferred_place_repository.create_for_kind.assert_called_once()


@pytest.mark.unit
class TestProfileToDictLabelBranch:
    """Covers 1189->1191 — teaching place with falsy label."""

    def test_teaching_place_empty_label_excluded(self):
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []

        place = MagicMock()
        place.kind = "teaching_location"
        place.position = 0
        place.address = "123 St"
        place.label = ""
        place.approx_lat = None
        place.approx_lng = None
        place.neighborhood = None

        profile = _make_mock_profile()
        profile.user.preferred_places = [place]

        result = svc._profile_to_dict(profile)
        assert len(result["preferred_teaching_locations"]) == 1
        assert "label" not in result["preferred_teaching_locations"][0]

    def test_teaching_place_with_label_included(self):
        svc = _make_service()
        svc.service_area_repository.list_for_instructor.return_value = []

        place = MagicMock()
        place.kind = "teaching_location"
        place.position = 0
        place.address = "123 St"
        place.label = "Studio"
        place.approx_lat = None
        place.approx_lng = None
        place.neighborhood = None

        profile = _make_mock_profile()
        profile.user.preferred_places = [place]

        result = svc._profile_to_dict(profile)
        assert result["preferred_teaching_locations"][0]["label"] == "Studio"


@pytest.mark.unit
class TestGetAvailableCatalogServicesCacheBranches:
    """Covers 1359->1367, 1362->1364, 1374->1378, 1378->1383, 1380->1383."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "s-1"}]
        result = svc.get_available_catalog_services()
        assert result == [{"id": "s-1"}]

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_active_services_with_categories.return_value = []
        svc.get_available_catalog_services()
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        svc.catalog_repository.get_active_services_with_categories.return_value = []
        result = svc.get_available_catalog_services()
        assert result == []

    @patch.dict("os.environ", {"AVAILABILITY_PERF_DEBUG": "1"})
    def test_debug_mode_cache_hit(self):

        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "s-1"}]
        result = svc.get_available_catalog_services()
        assert result == [{"id": "s-1"}]

    @patch.dict("os.environ", {"AVAILABILITY_PERF_DEBUG": "1"})
    def test_debug_mode_cache_miss_and_store(self):

        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_active_services_with_categories.return_value = []
        svc.get_available_catalog_services()
        svc.cache_service.set.assert_called_once()


@pytest.mark.unit
class TestGetServiceCategoriesCacheBranches:
    """Covers 1390->1396 and 1410->1414."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "c-1"}]
        result = svc.get_service_categories()
        assert result == [{"id": "c-1"}]

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        cat = MagicMock()
        cat.id = "c-1"
        cat.name = "Music"
        cat.subtitle = "sub"
        cat.description = "desc"
        cat.display_order = 1
        cat.icon_name = "icon"
        svc.category_repository.get_all_active.return_value = [cat]
        svc.get_service_categories()
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        cat = MagicMock()
        cat.id = "c-1"
        cat.name = "Music"
        cat.subtitle = "sub"
        cat.description = "desc"
        cat.display_order = 1
        cat.icon_name = "icon"
        svc.category_repository.get_all_active.return_value = [cat]
        result = svc.get_service_categories()
        assert len(result) == 1


@pytest.mark.unit
class TestUpdateFilterSelectionsMissed:
    """Covers 1579 (catalog not found) and 1592->1595 (cache invalidation)."""

    def test_catalog_not_found(self):
        from app.core.exceptions import NotFoundException

        svc = _make_service()
        svc.profile_repository.find_one_by.return_value = MagicMock(id="p-1")
        svc.service_repository.find_one_by.return_value = MagicMock(
            instructor_profile_id="p-1", service_catalog_id="cat-1"
        )
        svc.catalog_repository.get_by_id.return_value = None
        with pytest.raises(NotFoundException, match="Catalog service not found"):
            svc.update_filter_selections("inst-1", "svc-1", {"level": ["beginner"]})

    def test_cache_invalidated_after_update(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc._invalidate_instructor_caches = MagicMock()
        profile = MagicMock(id="p-1")
        svc.profile_repository.find_one_by.return_value = profile
        svc_obj = MagicMock(instructor_profile_id="p-1", service_catalog_id="cat-1")
        svc.service_repository.find_one_by.return_value = svc_obj
        catalog = MagicMock(subcategory_id="sub-1")
        svc.catalog_repository.get_by_id.return_value = catalog
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (True, [])

        with patch.object(svc, "_instructor_service_to_dict", return_value={"id": "svc-1"}):
            with patch("app.services.instructor_service.invalidate_on_service_change"):
                svc.update_filter_selections("inst-1", "svc-1", {"level": ["beginner"]})

        svc._invalidate_instructor_caches.assert_called_once()

    def test_no_cache_skips_invalidation(self):
        svc = _make_service()
        svc.cache_service = None
        profile = MagicMock(id="p-1")
        svc.profile_repository.find_one_by.return_value = profile
        svc_obj = MagicMock(instructor_profile_id="p-1", service_catalog_id="cat-1")
        svc.service_repository.find_one_by.return_value = svc_obj
        catalog = MagicMock(subcategory_id="sub-1")
        svc.catalog_repository.get_by_id.return_value = catalog
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (True, [])

        with patch.object(svc, "_instructor_service_to_dict", return_value={"id": "svc-1"}):
            with patch("app.services.instructor_service.invalidate_on_service_change"):
                result = svc.update_filter_selections("inst-1", "svc-1", {"level": ["beginner"]})
        assert result == {"id": "svc-1"}


@pytest.mark.unit
class TestSearchServicesEnhancedMissed:
    """Covers 1774->1781 and 1784->1767."""

    def test_with_price_filter(self):
        svc = _make_service()
        service_mock = MagicMock()
        service_mock.id = "s-1"
        service_mock.subcategory_id = "sub-1"
        service_mock.name = "Piano"
        service_mock.slug = "piano"
        service_mock.description = "desc"
        service_mock.search_terms = []
        service_mock.eligible_age_groups = []
        service_mock.display_order = 1
        service_mock.online_capable = True
        service_mock.requires_certification = False
        service_mock.category_name = "Music"

        svc.catalog_repository.search_services.return_value = [service_mock]
        analytics = MagicMock()
        analytics.to_dict.return_value = {}
        svc.analytics_repository.get_or_create.return_value = analytics

        inst_svc = MagicMock()
        inst_svc.hourly_rate = 75.0
        svc.service_repository.find_by.return_value = [inst_svc]

        result = svc.search_services_enhanced(
            query_text="piano", min_price=50.0, max_price=100.0
        )
        assert "matching_instructors" in result["services"][0]
        svc.analytics_repository.increment_search_count.assert_called()

    def test_no_price_filter_no_matching_instructors_key(self):
        svc = _make_service()
        service_mock = MagicMock()
        service_mock.id = "s-1"
        service_mock.subcategory_id = "sub-1"
        service_mock.name = "Piano"
        service_mock.slug = "piano"
        service_mock.description = "desc"
        service_mock.search_terms = []
        service_mock.eligible_age_groups = []
        service_mock.display_order = 1
        service_mock.online_capable = True
        service_mock.requires_certification = False
        service_mock.category_name = "Music"

        svc.catalog_repository.search_services.return_value = [service_mock]
        analytics = MagicMock()
        analytics.to_dict.return_value = {}
        svc.analytics_repository.get_or_create.return_value = analytics

        result = svc.search_services_enhanced()
        assert "matching_instructors" not in result["services"][0]


@pytest.mark.unit
class TestGetTopServicesPerCategoryCacheBranches:
    """Covers 1851->1858 and 1911->1915."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = {"categories": []}
        result = svc.get_top_services_per_category()
        assert result == {"categories": []}

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.category_repository.get_all_active.return_value = []
        svc.get_top_services_per_category()
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        svc.category_repository.get_all_active.return_value = []
        result = svc.get_top_services_per_category()
        assert "categories" in result


@pytest.mark.unit
class TestGetAllServicesWithInstructorsCacheBranches:
    """Covers 1931->1938, 2004->2009, 2033->2037."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = {"categories": []}
        result = svc.get_all_services_with_instructors()
        assert result == {"categories": []}

    def test_cache_miss_with_price_range(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        cat = MagicMock()
        cat.id = "c-1"
        cat.name = "Music"
        cat.subtitle = "sub"
        cat.description = "desc"
        cat.icon_name = "icon"
        cat.display_order = 1
        svc.category_repository.get_all_active.return_value = [cat]

        service = MagicMock()
        service.id = "s-1"
        service.subcategory_id = "sub-1"
        service.name = "Piano"
        service.slug = "piano"
        service.description = "desc"
        service.search_terms = []
        service.eligible_age_groups = []
        service.display_order = 1
        service.online_capable = True
        service.requires_certification = False
        service.is_active = True
        svc.catalog_repository.get_active_services_with_categories.return_value = [service]

        analytics = MagicMock()
        analytics.active_instructors = 2
        analytics.demand_score = 50
        analytics.is_trending = False
        svc.analytics_repository.get_or_create.return_value = analytics

        inst_svc = MagicMock()
        inst_svc.hourly_rate = 75.0
        svc.service_repository.find_by.return_value = [inst_svc]

        result = svc.get_all_services_with_instructors()
        assert "actual_min_price" in result["categories"][0]["services"][0]
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        svc.category_repository.get_all_active.return_value = []
        result = svc.get_all_services_with_instructors()
        assert "categories" in result


@pytest.mark.unit
class TestGetCategoriesWithSubcategoriesCacheBranches:
    """Covers 2045->2050 and 2075->2077."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "c-1"}]
        result = svc.get_categories_with_subcategories()
        assert result == [{"id": "c-1"}]

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_categories_with_subcategories.return_value = []
        svc.get_categories_with_subcategories()
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        svc.catalog_repository.get_categories_with_subcategories.return_value = []
        result = svc.get_categories_with_subcategories()
        assert result == []


@pytest.mark.unit
class TestGetCategoryTreeCacheBranches:
    """Covers 2083->2088 and 2114->2116."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = {"id": "c-1"}
        result = svc.get_category_tree("c-1")
        assert result == {"id": "c-1"}

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        cat = MagicMock()
        cat.id = "c-1"
        cat.name = "Music"
        cat.subtitle = "sub"
        cat.description = "desc"
        cat.display_order = 1
        cat.icon_name = "icon"
        cat.subcategories = []
        svc.catalog_repository.get_category_tree.return_value = cat
        svc.get_category_tree("c-1")
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        cat = MagicMock()
        cat.id = "c-1"
        cat.name = "Music"
        cat.subtitle = "sub"
        cat.description = "desc"
        cat.display_order = 1
        cat.icon_name = "icon"
        cat.subcategories = []
        svc.catalog_repository.get_category_tree.return_value = cat
        result = svc.get_category_tree("c-1")
        assert result["id"] == "c-1"


@pytest.mark.unit
class TestGetSubcategoryFiltersCacheBranches:
    """Covers 2149->2154 and 2156->2158."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"filter": "level"}]
        result = svc.get_subcategory_filters("sub-1")
        assert result == [{"filter": "level"}]

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.taxonomy_filter_repository.get_filters_for_subcategory.return_value = []
        svc.get_subcategory_filters("sub-1")
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        svc.taxonomy_filter_repository.get_filters_for_subcategory.return_value = [{"x": 1}]
        result = svc.get_subcategory_filters("sub-1")
        assert result == [{"x": 1}]


@pytest.mark.unit
class TestGetServicesByAgeGroupCacheBranches:
    """Covers 2179->2184 and 2187->2189."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "s-1"}]
        result = svc.get_services_by_age_group("kids")
        assert result == [{"id": "s-1"}]

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_services_by_eligible_age_group.return_value = []
        svc.get_services_by_age_group("kids")
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        svc.catalog_repository.get_services_by_eligible_age_group.return_value = []
        result = svc.get_services_by_age_group("kids")
        assert result == []


@pytest.mark.unit
class TestGetKidsAvailableServicesCacheBranches:
    """Covers 2199->2205 and 2207->2210."""

    def test_cache_hit(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "s-1"}]
        result = svc.get_kids_available_services()
        assert result == [{"id": "s-1"}]

    def test_cache_miss_stores(self):
        svc = _make_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_services_available_for_kids_minimal.return_value = []
        svc.get_kids_available_services()
        svc.cache_service.set.assert_called_once()

    def test_no_cache_service(self):
        svc = _make_service()
        svc.cache_service = None
        svc.catalog_repository.get_services_available_for_kids_minimal.return_value = []
        result = svc.get_kids_available_services()
        assert result == []


@pytest.mark.unit
class TestTeachingLocationNeighborhoodWithDistrict:
    """Covers 1110 — existing neighborhood + district concatenation."""

    def test_neighborhood_and_district_concatenated(self):
        svc = _make_service()
        svc.preferred_place_repository.list_for_instructor_and_kind.return_value = []
        svc.preferred_place_repository.delete_for_kind = MagicMock()
        svc.preferred_place_repository.flush = MagicMock()
        svc.preferred_place_repository.create_for_kind = MagicMock()
        svc.db = MagicMock()

        item = MagicMock()
        item.address = "456 Oak Ave"
        item.label = None

        mock_geocoded = MagicMock()
        mock_geocoded.latitude = 40.7
        mock_geocoded.longitude = -73.9
        mock_geocoded.provider_id = None
        mock_geocoded.neighborhood = "SoHo"
        mock_geocoded.city = None
        mock_geocoded.state = None

        with patch("app.services.instructor_service.create_geocoding_provider") as gp:
            gp.return_value = MagicMock()
            with patch("app.services.instructor_service.anyio") as mock_anyio:
                mock_anyio.run.return_value = mock_geocoded
                with patch("app.services.instructor_service.jitter_coordinates", return_value=(40.71, -73.91)):
                    with patch("app.services.instructor_service.LocationEnrichmentService") as les:
                        les.return_value.enrich.return_value = {
                            "neighborhood": None, "district": "Manhattan"
                        }
                        svc._replace_preferred_places("USR_01", "teaching_location", [item])

        call_kwargs = svc.preferred_place_repository.create_for_kind.call_args
        assert call_kwargs.kwargs.get("neighborhood") == "SoHo, Manhattan"


@pytest.mark.unit
class TestGetInstructorsFilteredTaxonomyBranches:
    """Covers taxonomy filter branches 320->318, matching_service_ids."""

    def test_service_id_none_skipped(self):
        """320->318: service_id is None => skip (don't add to candidates)."""
        svc = _make_service()
        svc.profile_repository.find_by_filters.return_value = [MagicMock()]
        svc.service_area_repository.list_for_instructor.return_value = []
        svc.preferred_place_repository.list_for_instructor.return_value = []

        with patch.object(svc, "_profile_to_dict") as ptd:
            ptd.return_value = {
                "services": [{"id": None, "is_active": True}],
                "user": None,
            }
            result = svc.get_instructors_filtered(
                taxonomy_filter_selections={"level": ["beginner"]},
                subcategory_id="sub-1",
            )
        assert result["instructors"] == []

    def test_matching_service_ids_filters_instructors(self):
        """matching_service_ids found => instructors with matching services only."""
        svc = _make_service()
        svc.profile_repository.find_by_filters.return_value = [MagicMock()]
        svc.service_area_repository.list_for_instructor.return_value = []
        svc.preferred_place_repository.list_for_instructor.return_value = []
        svc.taxonomy_filter_repository.find_matching_service_ids.return_value = {"svc-1"}

        with patch.object(svc, "_profile_to_dict") as ptd:
            ptd.return_value = {
                "services": [
                    {"id": "svc-1", "is_active": True},
                    {"id": "svc-2", "is_active": True},
                ],
                "user": None,
            }
            result = svc.get_instructors_filtered(
                taxonomy_filter_selections={"level": ["beginner"]},
            )
        assert len(result["instructors"]) == 1
        assert len(result["instructors"][0]["services"]) == 1
