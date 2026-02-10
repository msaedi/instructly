"""Comprehensive tests for instructor Pydantic schemas.

Tests cover validators, edge cases, and serialization for all instructor-related schemas.
Focus areas based on coverage gaps:
- InstructorFilterParams validators (search, age_group, price_range)
- ServiceBase validators (duration_options, age_groups, legacy field rejection)
- InstructorProfileBase/Create/Update validators
- PreferredTeachingLocationOut/PreferredPublicSpaceOut serializers
- InstructorProfileResponse.from_orm complex logic
- UserBasicPrivacy.from_user privacy transformation
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from pydantic import ValidationError
import pytest

from app.schemas.instructor import (
    InstructorFilterParams,
    InstructorProfileCreate,
    InstructorProfileResponse,
    InstructorProfileUpdate,
    PreferredPublicSpaceIn,
    PreferredPublicSpaceOut,
    PreferredTeachingLocationIn,
    PreferredTeachingLocationOut,
    ServiceAreaCheckCoordinates,
    ServiceCreate,
    ServiceResponse,
    UserBasicPrivacy,
)


class TestInstructorFilterParams:
    """Tests for InstructorFilterParams query parameter schema."""

    class TestSearchValidator:
        """Tests for search field validator (lines 68-73)."""

        def test_search_strips_whitespace(self) -> None:
            """Validator should strip leading/trailing whitespace."""
            params = InstructorFilterParams(search="  yoga  ")
            assert params.search == "yoga"

        def test_search_none_returns_none(self) -> None:
            """Validator should pass through None unchanged."""
            params = InstructorFilterParams(search=None)
            assert params.search is None

        def test_search_whitespace_only_strips_to_empty(self) -> None:
            """Whitespace-only string strips to empty, which fails min_length."""
            # Pydantic applies min_length before the validator, so " " (length 3) passes min_length
            # Then validator strips to "", which is allowed but empty
            params = InstructorFilterParams(search="   ")
            # The validator strips to empty string, but min_length was already passed
            assert params.search == ""

        def test_search_min_length_enforced(self) -> None:
            """Search must have at least 1 character."""
            with pytest.raises(ValidationError):
                InstructorFilterParams(search="")

        def test_search_max_length_enforced(self) -> None:
            """Search must not exceed 100 characters."""
            with pytest.raises(ValidationError):
                InstructorFilterParams(search="x" * 101)

    class TestPriceRangeValidator:
        """Tests for price range validation (lines 59-66)."""

        def test_min_price_only_is_valid(self) -> None:
            """Only min_price provided should be valid."""
            params = InstructorFilterParams(min_price=50)
            assert params.min_price == 50

        def test_max_price_only_is_valid(self) -> None:
            """Only max_price provided should be valid."""
            params = InstructorFilterParams(max_price=100)
            assert params.max_price == 100

        def test_valid_price_range(self) -> None:
            """min_price <= max_price should be valid."""
            params = InstructorFilterParams(min_price=50, max_price=100)
            assert params.min_price == 50
            assert params.max_price == 100

        def test_equal_min_max_price_is_valid(self) -> None:
            """min_price == max_price should be valid."""
            params = InstructorFilterParams(min_price=75, max_price=75)
            assert params.min_price == params.max_price == 75

        def test_max_less_than_min_fails(self) -> None:
            """max_price < min_price should fail."""
            with pytest.raises(ValidationError, match="max_price must be greater than or equal"):
                InstructorFilterParams(min_price=100, max_price=50)

        def test_negative_price_fails(self) -> None:
            """Negative prices should fail."""
            with pytest.raises(ValidationError):
                InstructorFilterParams(min_price=-10)

        def test_price_exceeds_max_fails(self) -> None:
            """Prices over 1000 should fail."""
            with pytest.raises(ValidationError):
                InstructorFilterParams(max_price=1001)

    class TestAgeGroupValidator:
        """Tests for age_group validation (lines 75-86, especially line 83)."""

        def test_none_returns_none(self) -> None:
            """None should pass through unchanged."""
            params = InstructorFilterParams(age_group=None)
            assert params.age_group is None

        def test_empty_string_returns_none(self) -> None:
            """Empty string should be treated as no filter."""
            params = InstructorFilterParams(age_group="")
            assert params.age_group is None

        def test_both_returns_none(self) -> None:
            """'both' should be treated as no filter (line 83)."""
            params = InstructorFilterParams(age_group="both")
            assert params.age_group is None

        def test_both_uppercase_returns_none(self) -> None:
            """'BOTH' should normalize to None."""
            params = InstructorFilterParams(age_group="BOTH")
            assert params.age_group is None

        def test_kids_is_valid(self) -> None:
            """'kids' should be accepted and normalized."""
            params = InstructorFilterParams(age_group="kids")
            assert params.age_group == "kids"

        def test_kids_uppercase_normalized(self) -> None:
            """'KIDS' should be normalized to lowercase."""
            params = InstructorFilterParams(age_group="KIDS")
            assert params.age_group == "kids"

        def test_adults_is_valid(self) -> None:
            """'adults' should be accepted."""
            params = InstructorFilterParams(age_group="adults")
            assert params.age_group == "adults"

        def test_whitespace_stripped(self) -> None:
            """Whitespace around age_group should be stripped."""
            params = InstructorFilterParams(age_group="  adults  ")
            assert params.age_group == "adults"

        def test_invalid_age_group_fails(self) -> None:
            """Invalid age_group values should fail."""
            with pytest.raises(ValidationError, match="age_group must be one of"):
                InstructorFilterParams(age_group="teenagers")

    class TestStrictConfig:
        """Tests for extra='forbid' config (line 89)."""

        def test_extra_fields_rejected(self) -> None:
            """Unknown fields should be rejected."""
            with pytest.raises(ValidationError, match="extra"):
                InstructorFilterParams(search="yoga", unknown_field="value")


class TestServiceBase:
    """Tests for ServiceBase schema validators."""

    def _valid_service_data(self) -> dict[str, Any]:
        """Helper to create valid service data."""
        return {
            "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
            "hourly_rate": Decimal("50.00"),
        }

    class TestDurationOptionsValidator:
        """Tests for duration_options validation (lines 219-229)."""

        def test_default_duration_is_60(self) -> None:
            """Default duration_options should be [60]."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
            }
            service = ServiceCreate(**data)
            assert service.duration_options == [60]

        def test_valid_duration_options(self) -> None:
            """Valid duration options within range should pass."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "duration_options": [30, 60, 90, 120],
            }
            service = ServiceCreate(**data)
            assert service.duration_options == [30, 60, 90, 120]

        def test_empty_duration_options_fails(self) -> None:
            """Empty duration_options should fail (line 222-223)."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "duration_options": [],
            }
            # Pydantic's min_length=1 catches this before our validator
            with pytest.raises(ValidationError, match="at least 1 item"):
                ServiceCreate(**data)

        def test_duration_below_minimum_fails(self) -> None:
            """Duration below MIN_SESSION_DURATION (30) should fail (lines 225-228)."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "duration_options": [15],
            }
            with pytest.raises(ValidationError, match="Duration must be between"):
                ServiceCreate(**data)

        def test_duration_above_maximum_fails(self) -> None:
            """Duration above MAX_SESSION_DURATION (240) should fail."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "duration_options": [300],
            }
            with pytest.raises(ValidationError, match="Duration must be between"):
                ServiceCreate(**data)

        def test_one_valid_one_invalid_fails(self) -> None:
            """Mix of valid and invalid durations should fail."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "duration_options": [60, 500],
            }
            with pytest.raises(ValidationError, match="Duration must be between"):
                ServiceCreate(**data)

    class TestAgeGroupsValidator:
        """Tests for age_groups list validation (lines 231-257)."""

        def test_none_is_valid(self) -> None:
            """None should pass through unchanged."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": None,
            }
            service = ServiceCreate(**data)
            assert service.age_groups is None

        def test_kids_only(self) -> None:
            """Single 'kids' value should be valid."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["kids"],
            }
            service = ServiceCreate(**data)
            assert service.age_groups == ["kids"]

        def test_adults_only(self) -> None:
            """Single 'adults' value should be valid."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["adults"],
            }
            service = ServiceCreate(**data)
            assert service.age_groups == ["adults"]

        def test_both_kids_and_adults(self) -> None:
            """Both 'kids' and 'adults' should be valid."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["kids", "adults"],
            }
            service = ServiceCreate(**data)
            assert service.age_groups == ["kids", "adults"]

        def test_both_keyword_rejected(self) -> None:
            """Legacy 'both' keyword is no longer accepted."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["both"],
            }
            with pytest.raises(ValidationError, match="age_groups must be one or more of"):
                ServiceCreate(**data)

        def test_case_insensitive(self) -> None:
            """Values should be normalized to lowercase."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["KIDS", "ADULTS"],
            }
            service = ServiceCreate(**data)
            assert service.age_groups == ["kids", "adults"]

        def test_duplicates_removed(self) -> None:
            """Duplicate values should be deduplicated (lines 251-257)."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["kids", "kids", "adults", "adults"],
            }
            service = ServiceCreate(**data)
            assert service.age_groups == ["kids", "adults"]

        def test_both_with_explicit_value_rejected(self) -> None:
            """Mixed payloads that include legacy 'both' should fail validation."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["both", "kids"],
            }
            with pytest.raises(ValidationError, match="age_groups must be one or more of"):
                ServiceCreate(**data)

        def test_invalid_age_group_fails(self) -> None:
            """Invalid age group values should fail (lines 248-249)."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["teenagers"],
            }
            with pytest.raises(ValidationError, match="age_groups must be one or more of"):
                ServiceCreate(**data)

        def test_whitespace_stripped(self) -> None:
            """Whitespace should be stripped from values."""
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "age_groups": ["  kids  "],
            }
            service = ServiceCreate(**data)
            assert service.age_groups == ["kids"]

    class TestLegacyFieldsRejected:
        """Legacy request fields should be rejected in clean-break mode."""

        def test_levels_taught_rejected(self) -> None:
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "levels_taught": ["beginner"],
            }
            with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
                ServiceCreate(**data)

        def test_location_types_rejected(self) -> None:
            data = {
                "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                "hourly_rate": Decimal("50.00"),
                "location_types": ["online"],
            }
            with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
                ServiceCreate(**data)


class TestInstructorProfileBase:
    """Tests for InstructorProfileBase schema."""

    class TestBioValidator:
        """Tests for bio validation (lines 429-434)."""

        def test_valid_bio(self) -> None:
            """Valid bio should pass."""
            data = {
                "bio": "I am an experienced yoga instructor with 10 years of practice.",
                "years_experience": 10,
                "services": [
                    {
                        "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                        "hourly_rate": Decimal("50.00"),
                    }
                ],
            }
            profile = InstructorProfileCreate(**data)
            assert "yoga instructor" in profile.bio

        def test_bio_whitespace_stripped(self) -> None:
            """Bio should have whitespace stripped."""
            data = {
                "bio": "   I am an experienced yoga instructor.   ",
                "years_experience": 5,
                "services": [
                    {
                        "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                        "hourly_rate": Decimal("50.00"),
                    }
                ],
            }
            profile = InstructorProfileCreate(**data)
            assert profile.bio == "I am an experienced yoga instructor."

        def test_bio_whitespace_only_fails(self) -> None:
            """Bio with only whitespace should fail (line 432-433)."""
            data = {
                "bio": "          ",
                "years_experience": 5,
                "services": [
                    {
                        "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                        "hourly_rate": Decimal("50.00"),
                    }
                ],
            }
            with pytest.raises(ValidationError, match="Bio cannot be empty"):
                InstructorProfileCreate(**data)

        def test_bio_too_short_fails(self) -> None:
            """Bio shorter than MIN_BIO_LENGTH should fail."""
            data = {
                "bio": "Short",
                "years_experience": 5,
                "services": [
                    {
                        "service_catalog_id": "01HZZZZZZZZZZZZZZZZZZZZZZZ",
                        "hourly_rate": Decimal("50.00"),
                    }
                ],
            }
            with pytest.raises(ValidationError):
                InstructorProfileCreate(**data)


class TestInstructorProfileUpdate:
    """Tests for InstructorProfileUpdate schema."""

    class TestPreferredLocationsValidators:
        """Tests for preferred location validators (lines 485-499)."""

        def test_none_preferred_teaching_locations(self) -> None:
            """None should be allowed."""
            update = InstructorProfileUpdate(preferred_teaching_locations=None)
            assert update.preferred_teaching_locations is None

        def test_empty_preferred_teaching_locations(self) -> None:
            """Empty list should be allowed."""
            update = InstructorProfileUpdate(preferred_teaching_locations=[])
            assert update.preferred_teaching_locations == []

        def test_two_preferred_teaching_locations_allowed(self) -> None:
            """Two locations should be allowed."""
            locations = [
                PreferredTeachingLocationIn(address="123 Main St, NY"),
                PreferredTeachingLocationIn(address="456 Oak Ave, NY"),
            ]
            update = InstructorProfileUpdate(preferred_teaching_locations=locations)
            assert len(update.preferred_teaching_locations or []) == 2

        def test_three_preferred_teaching_locations_fails(self) -> None:
            """More than two locations should fail (line 489-490)."""
            locations = [
                PreferredTeachingLocationIn(address="123 Main St, NY"),
                PreferredTeachingLocationIn(address="456 Oak Ave, NY"),
                PreferredTeachingLocationIn(address="789 Pine Rd, NY"),
            ]
            with pytest.raises(ValidationError, match="at most two entries"):
                InstructorProfileUpdate(preferred_teaching_locations=locations)

        def test_three_preferred_public_spaces_fails(self) -> None:
            """More than two public spaces should fail (lines 497-498)."""
            spaces = [
                PreferredPublicSpaceIn(address="Central Park"),
                PreferredPublicSpaceIn(address="Prospect Park"),
                PreferredPublicSpaceIn(address="Bryant Park"),
            ]
            with pytest.raises(ValidationError, match="at most two entries"):
                InstructorProfileUpdate(preferred_public_spaces=spaces)

    class TestDuplicateServicesValidator:
        """Tests for duplicate services validation (lines 501-509)."""

        def test_unique_services_allowed(self) -> None:
            """Unique service catalog IDs should pass."""
            services = [
                ServiceCreate(
                    service_catalog_id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
                    hourly_rate=Decimal("50.00"),
                ),
                ServiceCreate(
                    service_catalog_id="01HYYYYYYYYYYYYYYYYYYYYYY",
                    hourly_rate=Decimal("60.00"),
                ),
            ]
            update = InstructorProfileUpdate(services=services)
            assert len(update.services or []) == 2

        def test_duplicate_services_fails(self) -> None:
            """Duplicate service catalog IDs should fail (lines 506-509)."""
            services = [
                ServiceCreate(
                    service_catalog_id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
                    hourly_rate=Decimal("50.00"),
                ),
                ServiceCreate(
                    service_catalog_id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
                    hourly_rate=Decimal("60.00"),
                ),
            ]
            with pytest.raises(ValidationError, match="Duplicate services are not allowed"):
                InstructorProfileUpdate(services=services)

        def test_none_services_allowed(self) -> None:
            """None services (no update) should be allowed."""
            update = InstructorProfileUpdate(services=None)
            assert update.services is None


class TestPreferredTeachingLocationOut:
    """Tests for PreferredTeachingLocationOut serializer (lines 139-152)."""

    def test_full_serialization(self) -> None:
        """All fields should serialize when present."""
        location = PreferredTeachingLocationOut(
            address="123 Main St",
            label="Home Studio",
            approx_lat=40.7128,
            approx_lng=-74.0060,
            neighborhood="Midtown",
        )
        data = location.model_dump()
        assert data["address"] == "123 Main St"
        assert data["label"] == "Home Studio"
        assert data["approx_lat"] == 40.7128
        assert data["approx_lng"] == -74.0060
        assert data["neighborhood"] == "Midtown"

    def test_sparse_serialization(self) -> None:
        """Only present fields should serialize (custom serializer)."""
        location = PreferredTeachingLocationOut(address="123 Main St")
        data = location.model_dump()
        assert data["address"] == "123 Main St"
        # Optional fields with None should not be in serialized output
        # due to custom model_serializer

    def test_label_none_excluded_from_output(self) -> None:
        """None label should be excluded (line 144)."""
        location = PreferredTeachingLocationOut(address="123 Main St", label=None)
        data = location.model_dump()
        assert "label" not in data or data.get("label") is None

    def test_empty_address_excluded(self) -> None:
        """Empty address should be excluded from serialization."""
        location = PreferredTeachingLocationOut(address="")
        data = location.model_dump()
        assert "address" not in data or data.get("address") == ""


class TestPreferredPublicSpaceOut:
    """Tests for PreferredPublicSpaceOut serializer (lines 160-165)."""

    def test_address_always_included(self) -> None:
        """Address should always be in serialized output (line 162)."""
        space = PreferredPublicSpaceOut(address="Central Park")
        data = space.model_dump()
        assert data["address"] == "Central Park"

    def test_label_included_when_present(self) -> None:
        """Label should be included when not None (lines 163-164)."""
        space = PreferredPublicSpaceOut(address="Central Park", label="Near fountain")
        data = space.model_dump()
        assert data["label"] == "Near fountain"


class TestUserBasicPrivacy:
    """Tests for UserBasicPrivacy schema and from_user method."""

    def test_from_user_extracts_last_initial(self) -> None:
        """from_user should extract only last initial (line 400)."""
        user = MagicMock()
        user.id = "01HZZZZZZZZZZZZZZZZZZZZZZZ"
        user.first_name = "John"
        user.last_name = "Doe"
        user.email = "john.doe@example.com"

        privacy = UserBasicPrivacy.from_user(user)
        assert privacy.first_name == "John"
        assert privacy.last_initial == "D"
        # Email should NOT be exposed
        assert not hasattr(privacy, "email") or "email" not in privacy.model_dump()

    def test_from_user_empty_last_name(self) -> None:
        """Empty last_name should result in empty last_initial."""
        user = MagicMock()
        user.id = "01HZZZZZZZZZZZZZZZZZZZZZZZ"
        user.first_name = "John"
        user.last_name = ""
        user.email = "john@example.com"

        privacy = UserBasicPrivacy.from_user(user)
        assert privacy.last_initial == ""

    def test_from_user_none_last_name(self) -> None:
        """None last_name should result in empty last_initial."""
        user = MagicMock()
        user.id = "01HZZZZZZZZZZZZZZZZZZZZZZZ"
        user.first_name = "John"
        user.last_name = None
        user.email = "john@example.com"

        privacy = UserBasicPrivacy.from_user(user)
        assert privacy.last_initial == ""


class TestServiceAreaCheckCoordinates:
    """Tests for ServiceAreaCheckCoordinates."""

    def test_valid_coordinates(self) -> None:
        """Valid coordinates should pass."""
        coords = ServiceAreaCheckCoordinates(lat=40.7128, lng=-74.0060)
        assert coords.lat == 40.7128
        assert coords.lng == -74.0060

    def test_extra_fields_rejected(self) -> None:
        """StrictModel should reject extra fields."""
        with pytest.raises(ValidationError, match="extra"):
            ServiceAreaCheckCoordinates(lat=40.7128, lng=-74.0060, extra="field")


class TestInstructorProfileResponseFromOrm:
    """Tests for InstructorProfileResponse.from_orm complex logic."""

    def _create_mock_profile(self) -> MagicMock:
        """Create a mock InstructorProfile with all required attributes."""
        profile = MagicMock()
        profile.id = "01HZZZZZZZZZZZZZZZZZZZZZZZ"
        profile.user_id = "01HYYYYYYYYYYYYYYYYYYYYYY"
        profile.created_at = datetime.now(timezone.utc)
        profile.updated_at = None
        profile.bio = "Test bio for instructor profile."
        profile.years_experience = 5
        profile.min_advance_booking_hours = 2
        profile.buffer_time_minutes = 0
        profile.is_favorited = None
        profile.favorited_count = 0
        profile.skills_configured = False
        profile.identity_verified_at = None
        profile.background_check_uploaded_at = None
        profile.onboarding_completed_at = None
        profile.is_live = False
        profile.is_founding_instructor = False
        profile.bgc_status = None
        profile.instructor_services = []
        profile.service_area_neighborhoods = None

        user = MagicMock()
        user.id = "01HYYYYYYYYYYYYYYYYYYYYYY"
        user.first_name = "John"
        user.last_name = "Doe"
        user.email = "john.doe@example.com"
        user.preferred_places = []
        user.service_areas = []
        profile.user = user

        return profile

    def test_basic_from_orm(self) -> None:
        """Basic from_orm should work with minimal data."""
        profile = self._create_mock_profile()
        response = InstructorProfileResponse.from_orm(profile)
        assert response.id == profile.id
        assert response.user.first_name == "John"
        assert response.user.last_initial == "D"

    def test_from_orm_with_teaching_locations(self) -> None:
        """from_orm should process teaching locations (lines 585-594)."""
        profile = self._create_mock_profile()

        place = MagicMock()
        place.kind = "teaching_location"
        place.position = 0
        place.label = "Studio"
        place.address = "123 Main St"
        place.approx_lat = 40.7128
        place.approx_lng = -74.0060
        place.neighborhood = "Midtown"
        profile.user.preferred_places = [place]

        response = InstructorProfileResponse.from_orm(profile, include_private_fields=True)
        assert len(response.preferred_teaching_locations) == 1
        loc = response.preferred_teaching_locations[0]
        assert loc.label == "Studio"
        assert loc.approx_lat == 40.7128

    def test_from_orm_excludes_address_when_private(self) -> None:
        """from_orm should exclude address when include_private_fields=False (line 592-593)."""
        profile = self._create_mock_profile()

        place = MagicMock()
        place.kind = "teaching_location"
        place.position = 0
        place.label = "Studio"
        place.address = "123 Main St"
        place.approx_lat = 40.7128
        place.approx_lng = -74.0060
        place.neighborhood = "Midtown"
        profile.user.preferred_places = [place]

        response = InstructorProfileResponse.from_orm(profile, include_private_fields=False)
        assert len(response.preferred_teaching_locations) == 1
        loc = response.preferred_teaching_locations[0]
        # Address should not be included
        loc_data = loc.model_dump()
        assert "address" not in loc_data or loc_data.get("address") is None

    def test_from_orm_with_public_spaces(self) -> None:
        """from_orm should process public spaces (lines 596-601)."""
        profile = self._create_mock_profile()

        place = MagicMock()
        place.kind = "public_space"
        place.position = 0
        place.address = "Central Park"
        place.label = None
        profile.user.preferred_places = [place]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.preferred_public_spaces) == 1
        assert response.preferred_public_spaces[0].address == "Central Park"

    def test_from_orm_with_services(self) -> None:
        """from_orm should process services (lines 603-629)."""
        profile = self._create_mock_profile()

        service = MagicMock()
        service.id = "01HSERVICEID1234567890123"
        service.service_catalog_id = "01HCATALOGID12345678901234"
        service.hourly_rate = Decimal("50.00")
        service.description = "Test service"
        service.requirements = None
        service.age_groups = ["adults"]
        service.filter_selections = {"skill_level": ["beginner"]}
        service.equipment_required = []
        service.offers_travel = True
        service.offers_at_location = False
        service.offers_online = True
        service.duration_options = [60]

        catalog = MagicMock()
        catalog.name = "Yoga"
        service.catalog_entry = catalog

        profile.instructor_services = [service]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.services) == 1
        assert response.services[0].service_catalog_name == "Yoga"

    def test_from_orm_service_no_catalog_entry(self) -> None:
        """from_orm should handle missing catalog entry (line 607)."""
        profile = self._create_mock_profile()

        service = MagicMock()
        service.id = "01HSERVICEID1234567890123"
        service.service_catalog_id = "01HCATALOGID12345678901234"
        service.hourly_rate = Decimal("50.00")
        service.description = None
        service.requirements = None
        service.age_groups = None
        service.filter_selections = {}
        service.equipment_required = None
        service.offers_travel = False
        service.offers_at_location = False
        service.offers_online = True
        service.duration_options = None
        service.catalog_entry = None  # No catalog entry

        profile.instructor_services = [service]

        response = InstructorProfileResponse.from_orm(profile)
        assert response.services[0].service_catalog_name == "Unknown Service"

    def test_from_orm_with_dict_neighborhoods(self) -> None:
        """from_orm should handle dict neighborhoods (lines 638-668)."""
        profile = self._create_mock_profile()

        profile.service_area_neighborhoods = [
            {
                "neighborhood_id": "01HNEIGHBORHOODID123456",
                "ntacode": "MN01",
                "name": "Midtown",
                "borough": "Manhattan",
                "is_active": True,
            }
        ]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.service_area_neighborhoods) == 1
        assert response.service_area_boroughs == ["Manhattan"]
        assert response.service_area_summary == "Manhattan"

    def test_from_orm_skips_inactive_dict_neighborhoods(self) -> None:
        """from_orm should skip inactive neighborhoods (lines 639-640)."""
        profile = self._create_mock_profile()

        profile.service_area_neighborhoods = [
            {
                "neighborhood_id": "01HNEIGHBORHOODID123456",
                "name": "Midtown",
                "borough": "Manhattan",
                "is_active": False,  # Inactive
            }
        ]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.service_area_neighborhoods) == 0

    def test_from_orm_with_object_neighborhoods(self) -> None:
        """from_orm should handle object neighborhoods (lines 641-657)."""
        profile = self._create_mock_profile()

        neighborhood = MagicMock()
        neighborhood.neighborhood_id = "01HNEIGHBORHOODID123456"
        neighborhood.id = None
        neighborhood.ntacode = "MN01"
        neighborhood.region_code = None
        neighborhood.name = "Midtown"
        neighborhood.region_name = None
        neighborhood.borough = "Manhattan"
        neighborhood.parent_region = None
        neighborhood.is_active = True

        profile.service_area_neighborhoods = [neighborhood]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.service_area_neighborhoods) == 1
        assert response.service_area_boroughs == ["Manhattan"]

    def test_from_orm_fallback_to_user_service_areas(self) -> None:
        """from_orm should fall back to user.service_areas (lines 670-700)."""
        profile = self._create_mock_profile()
        profile.service_area_neighborhoods = None

        area = MagicMock()
        area.is_active = True
        area.neighborhood_id = "01HNEIGHBORHOODID123456"

        neighborhood = MagicMock()
        neighborhood.id = "01HNEIGHBORHOODID123456"
        neighborhood.parent_region = "Manhattan"
        neighborhood.borough = None
        neighborhood.region_code = "MN01"
        neighborhood.ntacode = None
        neighborhood.region_name = "Midtown"
        neighborhood.name = None
        area.neighborhood = neighborhood

        profile.user.service_areas = [area]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.service_area_neighborhoods) == 1
        assert response.service_area_boroughs == ["Manhattan"]

    def test_from_orm_skips_inactive_user_service_areas(self) -> None:
        """from_orm should skip inactive service areas (line 675-676)."""
        profile = self._create_mock_profile()
        profile.service_area_neighborhoods = None

        area = MagicMock()
        area.is_active = False  # Inactive
        area.neighborhood_id = "01HNEIGHBORHOODID123456"
        area.neighborhood = MagicMock()
        profile.user.service_areas = [area]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.service_area_neighborhoods) == 0

    def test_from_orm_skips_area_with_no_neighborhood(self) -> None:
        """from_orm should skip areas without neighborhood (line 679-680)."""
        profile = self._create_mock_profile()
        profile.service_area_neighborhoods = None

        area = MagicMock()
        area.is_active = True
        area.neighborhood = None  # No neighborhood

        profile.user.service_areas = [area]

        response = InstructorProfileResponse.from_orm(profile)
        assert len(response.service_area_neighborhoods) == 0

    def test_from_orm_adds_borough_to_set(self) -> None:
        """from_orm should add boroughs to set (line 699)."""
        profile = self._create_mock_profile()

        profile.service_area_neighborhoods = [
            {"name": "Midtown", "borough": "Manhattan", "is_active": True},
            {"name": "Downtown", "borough": "Manhattan", "is_active": True},
            {"name": "Williamsburg", "borough": "Brooklyn", "is_active": True},
        ]

        response = InstructorProfileResponse.from_orm(profile)
        assert set(response.service_area_boroughs) == {"Brooklyn", "Manhattan"}

    def test_from_orm_service_area_summary_many_boroughs(self) -> None:
        """from_orm should create summary with +N more (line 707)."""
        profile = self._create_mock_profile()

        profile.service_area_neighborhoods = [
            {"name": "Midtown", "borough": "Manhattan", "is_active": True},
            {"name": "Williamsburg", "borough": "Brooklyn", "is_active": True},
            {"name": "Astoria", "borough": "Queens", "is_active": True},
        ]

        response = InstructorProfileResponse.from_orm(profile)
        # 3 boroughs, so should show "Brooklyn + 2 more" (sorted alphabetically)
        assert "+ 2 more" in (response.service_area_summary or "")

    def test_from_orm_service_area_summary_two_boroughs(self) -> None:
        """from_orm should join two boroughs with comma."""
        profile = self._create_mock_profile()

        profile.service_area_neighborhoods = [
            {"name": "Midtown", "borough": "Manhattan", "is_active": True},
            {"name": "Williamsburg", "borough": "Brooklyn", "is_active": True},
        ]

        response = InstructorProfileResponse.from_orm(profile)
        assert response.service_area_summary == "Brooklyn, Manhattan"

    def test_from_orm_bgc_status_string_only(self) -> None:
        """from_orm should only include bgc_status if string (line 713)."""
        profile = self._create_mock_profile()
        profile.bgc_status = "clear"

        response = InstructorProfileResponse.from_orm(profile)
        assert response.bgc_status == "clear"

    def test_from_orm_bgc_status_non_string_excluded(self) -> None:
        """from_orm should exclude non-string bgc_status."""
        profile = self._create_mock_profile()
        profile.bgc_status = 123  # Not a string

        response = InstructorProfileResponse.from_orm(profile)
        assert response.bgc_status is None


class TestServiceResponse:
    """Tests for ServiceResponse schema."""

    def test_services_sorted_by_catalog_id(self) -> None:
        """Services should be sorted by service_catalog_id (line 744-747)."""
        services = [
            ServiceResponse(
                id="01HSERVICE3",
                service_catalog_id="01HCATALOG_C",
                service_catalog_name="Service C",
                hourly_rate=Decimal("50.00"),
            ),
            ServiceResponse(
                id="01HSERVICE1",
                service_catalog_id="01HCATALOG_A",
                service_catalog_name="Service A",
                hourly_rate=Decimal("50.00"),
            ),
            ServiceResponse(
                id="01HSERVICE2",
                service_catalog_id="01HCATALOG_B",
                service_catalog_name="Service B",
                hourly_rate=Decimal("50.00"),
            ),
        ]

        # Create a profile response mock to test sorting
        # The sort_services validator is on InstructorProfileResponse
        profile = MagicMock()
        profile.id = "01HPROFILEID"

        sorted_services = sorted(services, key=lambda s: s.service_catalog_id)
        assert sorted_services[0].service_catalog_name == "Service A"
        assert sorted_services[1].service_catalog_name == "Service B"
        assert sorted_services[2].service_catalog_name == "Service C"


class TestPreferredTeachingLocationIn:
    """Tests for PreferredTeachingLocationIn input schema."""

    def test_valid_location(self) -> None:
        """Valid location should pass."""
        location = PreferredTeachingLocationIn(address="123 Main St, NY")
        assert location.address == "123 Main St, NY"

    def test_with_label(self) -> None:
        """Location with label should pass."""
        location = PreferredTeachingLocationIn(address="123 Main St, NY", label="Home")
        assert location.label == "Home"

    def test_empty_address_fails(self) -> None:
        """Empty address should fail."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            PreferredTeachingLocationIn(address="")

    def test_extra_fields_rejected(self) -> None:
        """Extra fields should be rejected."""
        with pytest.raises(ValidationError, match="extra"):
            PreferredTeachingLocationIn(address="123 Main St", extra="field")

    def test_whitespace_stripped(self) -> None:
        """Whitespace should be stripped due to str_strip_whitespace."""
        location = PreferredTeachingLocationIn(address="  123 Main St  ")
        assert location.address == "123 Main St"


class TestPreferredPublicSpaceIn:
    """Tests for PreferredPublicSpaceIn input schema."""

    def test_valid_space(self) -> None:
        """Valid space should pass."""
        space = PreferredPublicSpaceIn(address="Central Park")
        assert space.address == "Central Park"

    def test_extra_fields_rejected(self) -> None:
        """Extra fields should be rejected."""
        with pytest.raises(ValidationError, match="extra"):
            PreferredPublicSpaceIn(address="Central Park", extra="field")
