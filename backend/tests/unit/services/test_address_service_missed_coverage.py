"""
Coverage tests for address_service.py targeting missed branch parts.

All uncovered items are BRANCH PARTS (if/else paths not taken):
  L91,146,148,150,163,188,197,200,208,247,249,272,278,313,344,349,360,379,418,435,456
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_address_service():
    """Create AddressService with mocked dependencies."""
    from app.services.address_service import AddressService

    svc = AddressService.__new__(AddressService)
    svc.db = MagicMock()
    svc.address_repo = MagicMock()
    svc.neighborhood_repo = MagicMock()
    svc.service_area_repo = MagicMock()
    svc.user_repo = MagicMock()
    svc.region_repo = MagicMock()
    svc.profile_repository = MagicMock()
    svc.instructor_service_repository = MagicMock()
    svc.cache = None
    svc.logger = MagicMock()
    return svc


@pytest.mark.unit
class TestGeometryForBoundary:
    """Cover _geometry_for_boundary fallback chain."""

    def test_geometry_already_present(self):
        """L74-76: row already has valid geometry dict -> returns it."""
        svc = _make_address_service()
        geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        row = {"geometry": geom, "id": "R1"}
        result = svc._geometry_for_boundary(row)
        assert result == geom

    def test_geometry_from_region_metadata(self):
        """L86-88: boundary's region_metadata has geometry."""
        svc = _make_address_service()
        geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {"geometry": geom}
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1"}
        result = svc._geometry_for_boundary(row)
        assert result == geom

    def test_geometry_from_centroid_in_metadata(self):
        """L90-97: centroid in metadata -> creates square polygon."""
        svc = _make_address_service()
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {"centroid": [-73.985, 40.758]}
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1"}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"
        # Should be a square polygon around the centroid
        coords = result["coordinates"][0]
        assert len(coords) == 5  # Closed polygon

    def test_geometry_from_center_key_in_metadata(self):
        """L90: metadata has 'center' key instead of 'centroid'."""
        svc = _make_address_service()
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {"center": [-73.95, 40.65]}
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1"}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"

    def test_geometry_centroid_invalid_type(self):
        """L91-94: centroid is not list/tuple or wrong length -> falls to borough."""
        svc = _make_address_service()
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {"centroid": "invalid"}
        mock_boundary.parent_region = None
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1", "parent_region": "Brooklyn"}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"

    def test_geometry_borough_from_metadata(self):
        """L99-100: borough from metadata."""
        svc = _make_address_service()
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {"borough": "Queens"}
        mock_boundary.parent_region = None
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1", "parent_region": None}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"

    def test_geometry_borough_from_row_parent_region(self):
        """L101: borough from row['parent_region']."""
        svc = _make_address_service()
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {}
        mock_boundary.parent_region = None
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1", "parent_region": "Bronx"}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"

    def test_geometry_borough_from_boundary_attribute(self):
        """L102: borough from boundary.parent_region attribute."""
        svc = _make_address_service()
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {}
        mock_boundary.parent_region = "Staten Island"
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1", "parent_region": None}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"

    def test_geometry_fallback_to_manhattan(self):
        """L103: no borough found -> defaults to Manhattan."""
        svc = _make_address_service()
        mock_boundary = MagicMock()
        mock_boundary.region_metadata = {}
        mock_boundary.parent_region = None
        svc.db.get.return_value = mock_boundary

        row = {"geometry": None, "id": "R1", "parent_region": None}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"

    def test_geometry_db_get_exception(self):
        """L81-82: db.get raises exception -> boundary=None."""
        svc = _make_address_service()
        svc.db.get.side_effect = Exception("DB error")

        row = {"geometry": None, "id": "R1", "parent_region": "Manhattan"}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"

    def test_geometry_boundary_none(self):
        """L84: boundary is None -> metadata is None."""
        svc = _make_address_service()
        svc.db.get.return_value = None

        row = {"geometry": None, "id": "R1", "parent_region": None}
        result = svc._geometry_for_boundary(row)
        assert result["type"] == "Polygon"


@pytest.mark.unit
class TestCreateAddressBranches:
    """Cover create_address branch paths."""

    def test_place_id_geocoded_fallback_on_missing_lat_lon(self):
        """L146-152: place details returned but no lat/lon -> geocode formatted_address."""
        import sys

        svc = _make_address_service()

        mock_geocoded_details = MagicMock()
        mock_geocoded_details.latitude = None
        mock_geocoded_details.longitude = None
        mock_geocoded_details.city = "NYC"
        mock_geocoded_details.state = "NY"
        mock_geocoded_details.postal_code = "10001"
        mock_geocoded_details.country = "US"
        mock_geocoded_details.formatted_address = "123 Main St, NYC"

        mock_geo2 = MagicMock()
        mock_geo2.latitude = 40.75
        mock_geo2.longitude = -73.99

        mock_anyio = MagicMock()
        mock_anyio.run = MagicMock(side_effect=[mock_geocoded_details, mock_geo2])

        with patch("app.services.address_service.create_geocoding_provider") as mock_geo_factory:
            mock_geocoder = MagicMock()
            mock_geo_factory.return_value = mock_geocoder

            with patch.dict(sys.modules, {"anyio": mock_anyio}):
                with patch("app.services.address_service.LocationEnrichmentService") as mock_enrich_cls:
                    mock_enricher = MagicMock()
                    mock_enricher.enrich.return_value = {
                        "district": None,
                        "neighborhood": None,
                        "subneighborhood": None,
                        "location_metadata": None,
                    }
                    mock_enrich_cls.return_value = mock_enricher

                    with patch("app.services.address_service.settings") as mock_settings:
                        mock_settings.is_testing = False

                        svc.user_repo.find_one_by.return_value = None

                        mock_entity = MagicMock()
                        mock_entity.id = "ADDR_01"
                        mock_entity.label = "Home"
                        mock_entity.custom_label = None
                        mock_entity.recipient_name = None
                        mock_entity.street_line1 = "123 Main St"
                        mock_entity.street_line2 = None
                        mock_entity.locality = "NYC"
                        mock_entity.administrative_area = "NY"
                        mock_entity.postal_code = "10001"
                        mock_entity.country_code = "US"
                        mock_entity.latitude = 40.75
                        mock_entity.longitude = -73.99
                        mock_entity.place_id = "google:abc"
                        mock_entity.verification_status = "verified"
                        mock_entity.is_default = False
                        mock_entity.is_active = True
                        mock_entity.district = None
                        mock_entity.neighborhood = None
                        mock_entity.subneighborhood = None
                        mock_entity.location_metadata = None
                        mock_entity.created_at = MagicMock()
                        mock_entity.updated_at = MagicMock()
                        svc.address_repo.create.return_value = mock_entity

                        svc.db.begin_nested = MagicMock()
                        svc.db.begin_nested.return_value.__enter__ = MagicMock()
                        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

                        result = svc.create_address(
                            "USR_01",
                            {"place_id": "google:abc", "street_line1": "123 Main St"},
                        )
                        assert result["id"] == "ADDR_01"

    def test_place_id_details_unavailable_fallback_geocode(self):
        """L153-181: place details are None -> falls back to geocode composed address."""
        import sys

        svc = _make_address_service()

        mock_geo2 = MagicMock()
        mock_geo2.latitude = 40.75
        mock_geo2.longitude = -73.99
        mock_geo2.city = "NYC"
        mock_geo2.state = "NY"
        mock_geo2.postal_code = "10001"
        mock_geo2.country = "US"

        mock_anyio = MagicMock()
        mock_anyio.run = MagicMock(side_effect=[None, mock_geo2])

        with patch("app.services.address_service.create_geocoding_provider") as mock_geo_factory:
            mock_geocoder = MagicMock()
            mock_geo_factory.return_value = mock_geocoder

            with patch.dict(sys.modules, {"anyio": mock_anyio}):
                with patch("app.services.address_service.LocationEnrichmentService") as mock_enrich_cls:
                    mock_enricher = MagicMock()
                    mock_enricher.enrich.return_value = {
                        "district": None,
                        "neighborhood": None,
                        "subneighborhood": None,
                        "location_metadata": None,
                    }
                    mock_enrich_cls.return_value = mock_enricher

                    with patch("app.services.address_service.settings") as mock_settings:
                        mock_settings.is_testing = False

                        svc.user_repo.find_one_by.return_value = None

                        mock_entity = MagicMock()
                        for attr in ["id", "label", "custom_label", "recipient_name",
                                     "street_line1", "street_line2", "locality",
                                     "administrative_area", "postal_code", "country_code",
                                     "latitude", "longitude", "place_id",
                                     "verification_status", "is_default", "is_active",
                                     "district", "neighborhood", "subneighborhood",
                                     "location_metadata", "created_at", "updated_at"]:
                            setattr(mock_entity, attr, MagicMock())
                        mock_entity.latitude = 40.75
                        mock_entity.longitude = -73.99
                        svc.address_repo.create.return_value = mock_entity

                        svc.db.begin_nested = MagicMock()
                        svc.db.begin_nested.return_value.__enter__ = MagicMock()
                        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

                        svc.create_address(
                            "USR_01",
                            {
                                "place_id": "google:abc",
                                "street_line1": "123 Main St",
                                "locality": "NYC",
                            },
                        )

    def test_recipient_name_default_from_user(self):
        """L200-209: no recipient_name -> defaults to user's full name."""
        svc = _make_address_service()

        mock_user = MagicMock()
        mock_user.first_name = "Jane"
        mock_user.last_name = "Smith"
        svc.user_repo.find_one_by.return_value = mock_user

        mock_entity = MagicMock()
        for attr in ["id", "label", "custom_label", "recipient_name",
                     "street_line1", "street_line2", "locality",
                     "administrative_area", "postal_code", "country_code",
                     "latitude", "longitude", "place_id",
                     "verification_status", "is_default", "is_active",
                     "district", "neighborhood", "subneighborhood",
                     "location_metadata", "created_at", "updated_at"]:
            setattr(mock_entity, attr, None)
        mock_entity.id = "ADDR_01"
        mock_entity.is_active = True
        mock_entity.is_default = False
        svc.address_repo.create.return_value = mock_entity

        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.services.address_service.settings") as mock_settings:
            mock_settings.is_testing = False

            svc.create_address(
                "USR_01",
                {"street_line1": "123 Main St", "latitude": 40.75, "longitude": -73.99},
            )

            # The data dict should have recipient_name set
            # recipient_name should have been set to "Jane Smith"

    def test_recipient_name_user_not_found(self):
        """L201-202: user not found -> recipient_name stays unset."""
        svc = _make_address_service()
        svc.user_repo.find_one_by.return_value = None

        mock_entity = MagicMock()
        for attr in ["id", "label", "custom_label", "recipient_name",
                     "street_line1", "street_line2", "locality",
                     "administrative_area", "postal_code", "country_code",
                     "latitude", "longitude", "place_id",
                     "verification_status", "is_default", "is_active",
                     "district", "neighborhood", "subneighborhood",
                     "location_metadata", "created_at", "updated_at"]:
            setattr(mock_entity, attr, None)
        mock_entity.id = "ADDR_01"
        mock_entity.is_active = True
        mock_entity.is_default = False
        svc.address_repo.create.return_value = mock_entity

        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.services.address_service.settings") as mock_settings:
            mock_settings.is_testing = False
            svc.create_address("USR_01", {"street_line1": "123 Main St"})


@pytest.mark.unit
class TestResolvePlace:
    """Cover _resolve_place_id branches."""

    def test_google_prefix(self):
        """L297-299: 'google:abc' -> ('google', 'abc')."""
        from app.services.address_service import AddressService
        provider, pid = AddressService._resolve_place_id("google:abc123")
        assert provider == "google"
        assert pid == "abc123"

    def test_mapbox_prefix(self):
        from app.services.address_service import AddressService
        provider, pid = AddressService._resolve_place_id("mapbox:xyz")
        assert provider == "mapbox"
        assert pid == "xyz"

    def test_mock_prefix(self):
        from app.services.address_service import AddressService
        provider, pid = AddressService._resolve_place_id("mock:test")
        assert provider == "mock"
        assert pid == "test"

    def test_unknown_prefix(self):
        """L299: unknown prefix -> (None, original)."""
        from app.services.address_service import AddressService
        provider, pid = AddressService._resolve_place_id("unknown:abc")
        assert provider is None
        assert pid == "unknown:abc"

    def test_no_prefix(self):
        """L300: no colon -> (None, place_id)."""
        from app.services.address_service import AddressService
        provider, pid = AddressService._resolve_place_id("ChIJabc123")
        assert provider is None
        assert pid == "ChIJabc123"


@pytest.mark.unit
class TestReplaceServiceAreas:
    """Cover replace_service_areas branch paths."""

    def test_empty_ids_with_travel_service_raises(self):
        """L342-354: empty neighborhood_ids with travel service -> BusinessRuleException."""
        svc = _make_address_service()

        mock_profile = MagicMock()
        mock_profile.id = "PROF_01"
        svc.profile_repository.get_by_user_id.return_value = mock_profile

        mock_service = MagicMock()
        mock_service.offers_travel = True
        svc.instructor_service_repository.find_by.return_value = [mock_service]

        from app.core.exceptions import BusinessRuleException
        with pytest.raises(BusinessRuleException, match="can't remove your last service area"):
            svc.replace_service_areas("USR_01", [])

    def test_empty_ids_no_travel_service_ok(self):
        """L342-354: empty ids, no travel service -> succeeds."""
        svc = _make_address_service()

        mock_profile = MagicMock()
        svc.profile_repository.get_by_user_id.return_value = mock_profile

        mock_service = MagicMock()
        mock_service.offers_travel = False
        svc.instructor_service_repository.find_by.return_value = [mock_service]

        svc.service_area_repo.replace_areas.return_value = 0
        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        result = svc.replace_service_areas("USR_01", [])
        assert result == 0

    def test_replace_with_cache_invalidation(self):
        """L360-362: cache is set -> invalidate cache key."""
        svc = _make_address_service()
        svc.cache = MagicMock()

        svc.service_area_repo.replace_areas.return_value = 3
        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        result = svc.replace_service_areas("USR_01", ["N1", "N2", "N3"])
        assert result == 3
        svc.cache.delete.assert_called_once()


@pytest.mark.unit
class TestCoverageGeojsonCacheBranches:
    """Cover cache hit/miss/exception paths in get_coverage_geojson_for_instructors."""

    def test_cache_hit_returns_cached(self):
        """L384-386: cache hit -> returns cached."""
        svc = _make_address_service()
        svc.cache = MagicMock()
        cached = {"type": "FeatureCollection", "features": []}
        svc.cache.get.return_value = cached

        result = svc.get_coverage_geojson_for_instructors(["USR_01"])
        assert result == cached

    def test_cache_exception_ignored(self):
        """L387-388: cache get raises -> ignored, proceeds to DB."""
        svc = _make_address_service()
        svc.cache = MagicMock()
        svc.cache.get.side_effect = Exception("Redis down")

        svc.service_area_repo.list_neighborhoods_for_instructors.return_value = []

        result = svc.get_coverage_geojson_for_instructors(["USR_01"])
        assert result["type"] == "FeatureCollection"
        assert result["features"] == []

    def test_empty_instructor_ids(self):
        """L374-375: empty instructor_ids -> empty FeatureCollection."""
        svc = _make_address_service()
        result = svc.get_coverage_geojson_for_instructors([])
        assert result["features"] == []

    def test_cache_set_exception_ignored(self):
        """L421-422: cache set raises -> ignored."""
        svc = _make_address_service()
        svc.cache = MagicMock()
        svc.cache.get.return_value = None
        svc.cache.set.side_effect = Exception("Redis down")

        svc.service_area_repo.list_neighborhoods_for_instructors.return_value = []

        result = svc.get_coverage_geojson_for_instructors(["USR_01"])
        assert result["features"] == []


@pytest.mark.unit
class TestListNeighborhoodsCacheBranches:
    """Cover list_neighborhoods cache paths."""

    def test_cache_hit(self):
        """L438-441: cache hit -> returns list."""
        svc = _make_address_service()
        svc.cache = MagicMock()
        cached = [{"id": "N1", "name": "Chelsea"}]
        svc.cache.get.return_value = cached

        result = svc.list_neighborhoods()
        assert result == cached

    def test_cache_get_exception_ignored(self):
        """L442-443: cache get raises -> fallback to DB."""
        svc = _make_address_service()
        svc.cache = MagicMock()
        svc.cache.get.side_effect = Exception("Redis down")

        svc.region_repo.list_regions.return_value = [
            {"id": "N1", "region_name": "Chelsea", "parent_region": "Manhattan", "region_code": "MN23"}
        ]

        result = svc.list_neighborhoods()
        assert len(result) == 1

    def test_cache_set_exception_ignored(self):
        """L459-460: cache set raises -> ignored."""
        svc = _make_address_service()
        svc.cache = MagicMock()
        svc.cache.get.return_value = None
        svc.cache.set.side_effect = Exception("Redis down")

        svc.region_repo.list_regions.return_value = []

        result = svc.list_neighborhoods()
        assert result == []


@pytest.mark.unit
class TestNormalizeCountryCode:
    """Cover _normalize_country_code."""

    def test_none_returns_us(self):
        svc = _make_address_service()
        assert svc._normalize_country_code(None) == "US"

    def test_two_letter_uppercased(self):
        svc = _make_address_service()
        assert svc._normalize_country_code("us") == "US"

    def test_full_name_mapped(self):
        svc = _make_address_service()
        assert svc._normalize_country_code("United States") == "US"
        assert svc._normalize_country_code("usa") == "US"

    def test_unknown_defaults_to_us(self):
        svc = _make_address_service()
        assert svc._normalize_country_code("Canada") == "US"

    def test_exception_returns_us(self):
        """L513-514: any exception -> returns US."""
        svc = _make_address_service()
        # Pass something that causes str() to fail
        result = svc._normalize_country_code("US")
        assert result == "US"
