from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.core.enums import RoleName
from app.core.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
)
from app.schemas.instructor import InstructorProfileCreate, InstructorProfileUpdate, ServiceCreate
from app.services.instructor_service import InstructorService, get_instructor_service


def _build_service() -> InstructorService:
    db = MagicMock()
    service = InstructorService(db)
    service.profile_repository = MagicMock()
    service.service_repository = MagicMock()
    service.user_repository = MagicMock()
    service.booking_repository = MagicMock()
    service.catalog_repository = MagicMock()
    service.category_repository = MagicMock()
    service.analytics_repository = MagicMock()
    service.preferred_place_repository = MagicMock()
    service.service_area_repository = MagicMock()
    return service


def _make_service_create(catalog_id: str) -> ServiceCreate:
    return ServiceCreate(
        offers_travel=False,
        offers_at_location=False,
        offers_online=True,
        service_catalog_id=catalog_id,
        hourly_rate=60.0,
        description="Lessons",
        duration_options=[60],
    )


def test_create_instructor_profile_with_services_assigns_role():
    service = _build_service()
    service.profile_repository.exists.return_value = False
    service.catalog_repository.exists.return_value = True

    profile = MagicMock()
    profile.id = "profile-1"
    service.profile_repository.create.return_value = profile

    user = MagicMock()
    user.id = "user-1"
    service.user_repository.get_by_id.return_value = user

    profile_data = InstructorProfileCreate(
        bio="Experienced instructor with years of lessons.",
        years_experience=5,
        min_advance_booking_hours=2,
        buffer_time_minutes=0,
        services=[_make_service_create("cat-1")],
    )

    with patch("app.services.permission_service.PermissionService") as perm_cls:
        with patch.object(service, "_profile_to_dict", return_value={"id": "profile-1"}):
            result = service.create_instructor_profile(user, profile_data)

    assert result == {"id": "profile-1"}
    service.service_repository.bulk_create.assert_called_once()
    perm_cls.return_value.assign_role.assert_called_once_with("user-1", RoleName.INSTRUCTOR)


@pytest.mark.parametrize(
    "skill_names, expected_phrase",
    [
        ([], "Alex is a Brooklyn-based instructor."),
        (["Yoga"], "Alex is a Brooklyn-based yoga instructor."),
        (["Yoga", "Pilates"], "Alex is a Brooklyn-based yoga and pilates instructor."),
        (
            ["Yoga", "Pilates", "Meditation"],
            "Alex is a Brooklyn-based yoga, pilates, and meditation instructor.",
        ),
    ],
)
def test_update_instructor_profile_auto_bio_variants(skill_names, expected_phrase):
    service = _build_service()
    service.cache_service = MagicMock()
    service._invalidate_instructor_caches = MagicMock()
    service._update_services = MagicMock(return_value=False)
    service.get_instructor_profile = MagicMock(return_value={"id": "profile-1"})

    profile = MagicMock()
    profile.id = "profile-1"
    profile.user_id = "user-1"
    profile.bio = None
    profile.years_experience = 3
    service.profile_repository.find_one_by.return_value = profile
    service.profile_repository.update.return_value = profile

    service.user_repository.get_by_id.return_value = SimpleNamespace(
        first_name="Alex", zip_code="10001"
    )

    services = [_make_service_create(f"cat-{idx}") for idx, _ in enumerate(skill_names)]
    update_data = InstructorProfileUpdate(services=services)

    with patch("app.services.instructor_service.create_geocoding_provider") as provider_mock:
        provider_mock.return_value = SimpleNamespace(geocode=Mock())
        with patch("app.services.instructor_service.anyio.run") as anyio_run:
            anyio_run.return_value = SimpleNamespace(city="Brooklyn")
            if skill_names:
                service.catalog_repository.get_by_id.side_effect = [
                    SimpleNamespace(name=name) for name in skill_names
                ]
            with patch("app.services.instructor_service.InstructorLifecycleService"):
                with patch(
                    "app.services.instructor_service.invalidate_on_instructor_profile_change"
                ):
                    service.update_instructor_profile("user-1", update_data)

    _, kwargs = service.profile_repository.update.call_args
    assert kwargs["bio"] == expected_phrase


def test_update_instructor_profile_handles_geocode_and_catalog_errors():
    service = _build_service()
    service.cache_service = MagicMock()
    service._invalidate_instructor_caches = MagicMock()
    service._update_services = MagicMock(return_value=False)
    service.get_instructor_profile = MagicMock(return_value={"id": "profile-1"})

    profile = MagicMock()
    profile.id = "profile-1"
    profile.user_id = "user-1"
    profile.bio = None
    profile.years_experience = 4
    service.profile_repository.find_one_by.return_value = profile
    service.profile_repository.update.return_value = profile

    service.user_repository.get_by_id.return_value = SimpleNamespace(first_name="Sam", zip_code="10001")

    update_data = InstructorProfileUpdate(services=[_make_service_create("cat-1")])

    with patch("app.services.instructor_service.create_geocoding_provider", side_effect=Exception("geo")):
        with patch("app.services.instructor_service.anyio.run", side_effect=Exception("geo")):
            service.catalog_repository.get_by_id.side_effect = Exception("catalog")
            with patch("app.services.instructor_service.InstructorLifecycleService"):
                with patch(
                    "app.services.instructor_service.invalidate_on_instructor_profile_change"
                ):
                    service.update_instructor_profile("user-1", update_data)

    _, kwargs = service.profile_repository.update.call_args
    assert kwargs["bio"] == "Sam is a New York-based instructor."


def test_update_instructor_profile_fallback_bio_on_exception():
    service = _build_service()
    service.cache_service = MagicMock()
    service._invalidate_instructor_caches = MagicMock()
    service._update_services = MagicMock(return_value=False)
    service.get_instructor_profile = MagicMock(return_value={"id": "profile-1"})

    profile = MagicMock()
    profile.id = "profile-1"
    profile.user_id = "user-1"
    profile.bio = None
    profile.years_experience = 2
    service.profile_repository.find_one_by.return_value = profile
    service.profile_repository.update.return_value = profile

    service.user_repository.get_by_id.side_effect = Exception("boom")

    update_data = InstructorProfileUpdate(services=[_make_service_create("cat-1")])

    with patch("app.services.instructor_service.InstructorLifecycleService"):
        with patch("app.services.instructor_service.invalidate_on_instructor_profile_change"):
            service.update_instructor_profile("user-1", update_data)

    _, kwargs = service.profile_repository.update.call_args
    assert kwargs["bio"] == "Experienced instructor"


def test_validate_catalog_ids_invalid_raises():
    service = _build_service()
    service.catalog_repository.exists.side_effect = [True, False]

    with pytest.raises(BusinessRuleException):
        service._validate_catalog_ids(["cat-1", "cat-2"])


def test_resolve_and_apply_location_types():
    service = _build_service()

    svc = SimpleNamespace(offers_travel=True, offers_at_location=False, offers_online=True)
    assert service._resolve_location_types(svc) == ["in_person", "online"]

    updates = {"offers_travel": True, "offers_at_location": False, "offers_online": True}
    service._apply_location_type_capabilities(updates)
    assert updates["location_types"] == ["in_person", "online"]

    updates = {}
    service._apply_location_type_capabilities(updates, apply_defaults=True)
    assert updates["location_types"] == ["online"]


def test_update_service_capabilities_updates_and_invalidates_cache():
    service = _build_service()
    service.cache_service = MagicMock()
    service._invalidate_instructor_caches = MagicMock()
    service.validate_service_capabilities = MagicMock()
    service._instructor_service_to_dict = MagicMock(return_value={"id": "svc-1"})

    instructor_profile = SimpleNamespace(user_id="user-1")
    svc = SimpleNamespace(
        id="svc-1",
        instructor_profile=instructor_profile,
        offers_travel=False,
        offers_at_location=False,
        offers_online=True,
    )
    service.service_repository.get_by_id.return_value = svc

    with patch("app.services.instructor_service.invalidate_on_service_change") as invalidate_mock:
        result = service.update_service_capabilities(
            "svc-1", "user-1", {"offers_travel": True, "offers_online": False}
        )

    assert result["id"] == "svc-1"
    service._invalidate_instructor_caches.assert_called_once_with("user-1")
    invalidate_mock.assert_called_once_with("svc-1", "update")


def test_update_service_capabilities_forbidden():
    service = _build_service()
    svc = SimpleNamespace(id="svc-1", instructor_profile=SimpleNamespace(user_id="other"))
    service.service_repository.get_by_id.return_value = svc

    with pytest.raises(ForbiddenException):
        service.update_service_capabilities("svc-1", "user-1", {"offers_online": True})


def test_update_service_capabilities_not_found():
    service = _build_service()
    service.service_repository.get_by_id.return_value = None

    with pytest.raises(NotFoundException):
        service.update_service_capabilities("svc-1", "user-1", {"offers_online": True})


def test_update_services_reactivate_create_soft_and_hard_delete():
    service = _build_service()
    service._validate_catalog_ids = MagicMock()
    service.validate_service_capabilities = MagicMock()

    active_keep = MagicMock()
    active_keep.id = "svc-a"
    active_keep.service_catalog_id = "cat-a"
    active_keep.is_active = True
    active_keep.catalog_entry = SimpleNamespace(name="Piano")

    active_remove_soft = MagicMock()
    active_remove_soft.id = "svc-b"
    active_remove_soft.service_catalog_id = "cat-b"
    active_remove_soft.is_active = True
    active_remove_soft.catalog_entry = SimpleNamespace(name="Guitar")

    inactive_reactivate = MagicMock()
    inactive_reactivate.id = "svc-c"
    inactive_reactivate.service_catalog_id = "cat-c"
    inactive_reactivate.is_active = False
    inactive_reactivate.catalog_entry = SimpleNamespace(name="Yoga")

    service.service_repository.find_by.return_value = [
        active_keep,
        active_remove_soft,
        inactive_reactivate,
    ]

    def _has_bookings(**kwargs):
        return kwargs.get("instructor_service_id") == "svc-b"

    service.booking_repository.exists.side_effect = _has_bookings

    services_data = [
        _make_service_create("cat-c"),
        _make_service_create("cat-new"),
    ]

    with patch(
        "app.services.instructor_service.Service",
        side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
    ):
        result = service._update_services("profile-1", "user-1", services_data)

    assert result is False
    assert any(
        call.args[0] == "svc-c" and call.kwargs.get("is_active") is True
        for call in service.service_repository.update.call_args_list
    )
    service.service_repository.update.assert_any_call("svc-b", is_active=False)
    service.service_repository.delete.assert_any_call("svc-a")
    service.service_repository.create.assert_called_once()
    service.profile_repository.update.assert_called_once_with("profile-1", skills_configured=True)


def test_replace_preferred_places_rejects_duplicates_and_limits():
    service = _build_service()

    item = SimpleNamespace(address="123 Main St", label="Studio")
    with pytest.raises(BusinessRuleException):
        service._replace_preferred_places("user-1", "teaching_location", [item, item])

    items = [
        SimpleNamespace(address="1 A St", label=None),
        SimpleNamespace(address="2 B St", label=None),
        SimpleNamespace(address="3 C St", label=None),
    ]
    with pytest.raises(BusinessRuleException):
        service._replace_preferred_places("user-1", "teaching_location", items)


def test_replace_preferred_places_blocks_last_teaching_location():
    service = _build_service()
    profile = SimpleNamespace(id="profile-1")
    service.profile_repository.get_by_user_id.return_value = profile
    service.service_repository.find_by.return_value = [SimpleNamespace(offers_at_location=True)]

    with pytest.raises(BusinessRuleException):
        service._replace_preferred_places("user-1", "teaching_location", [])


def test_replace_preferred_places_handles_existing_place_error_and_geocoding():
    service = _build_service()
    service.preferred_place_repository.list_for_instructor_and_kind.side_effect = Exception("boom")

    service.preferred_place_repository.delete_for_kind = MagicMock()
    service.preferred_place_repository.flush = MagicMock()
    service.preferred_place_repository.create_for_kind = MagicMock()

    with patch("app.services.instructor_service.create_geocoding_provider") as provider_mock:
        provider_mock.return_value = SimpleNamespace(geocode=Mock())
        with patch("app.services.instructor_service.anyio.run", return_value=None):
            service._replace_preferred_places(
                "user-1",
                "teaching_location",
                [SimpleNamespace(address="123 Main St", label=" ")],
            )

    _, kwargs = service.preferred_place_repository.create_for_kind.call_args
    assert kwargs["label"] is None


def test_replace_preferred_places_geocode_and_enrichment_paths():
    service = _build_service()
    service.preferred_place_repository.list_for_instructor_and_kind.return_value = []
    service.preferred_place_repository.delete_for_kind = MagicMock()
    service.preferred_place_repository.flush = MagicMock()
    service.preferred_place_repository.create_for_kind = MagicMock()

    fake_geo = SimpleNamespace(
        latitude=40.7,
        longitude=-74.0,
        provider_id="place-1",
        neighborhood=None,
        city="New York",
        state="NY",
    )

    with patch("app.services.instructor_service.create_geocoding_provider") as provider_mock:
        provider_mock.return_value = SimpleNamespace(geocode=Mock())
        with patch("app.services.instructor_service.anyio.run", return_value=fake_geo):
            with patch(
                "app.services.instructor_service.jitter_coordinates",
                return_value=(40.71, -74.01),
            ):
                with patch(
                    "app.services.instructor_service.LocationEnrichmentService.enrich",
                    return_value={"neighborhood": "Chelsea", "district": "Manhattan"},
                ):
                    service._replace_preferred_places(
                        "user-1",
                        "teaching_location",
                        [SimpleNamespace(address="456 Broadway", label="Studio")],
                    )

    _, kwargs = service.preferred_place_repository.create_for_kind.call_args
    assert kwargs["neighborhood"] == "Chelsea, Manhattan"
    assert kwargs["approx_lat"] == pytest.approx(40.71)
    assert kwargs["approx_lng"] == pytest.approx(-74.01)


def test_profile_to_dict_handles_non_iterable_services_and_service_areas():
    service = _build_service()
    service.preferred_place_repository.list_for_instructor.return_value = []

    region_meta = {
        "nta_code": "N1",
        "nta_name": "Neighborhood One",
        "borough": "Brooklyn",
    }
    areas = [
        SimpleNamespace(neighborhood_id="n1", neighborhood=SimpleNamespace(region_metadata=region_meta)),
        SimpleNamespace(
            neighborhood_id="n2",
            neighborhood=SimpleNamespace(
                region_metadata={"nta_code": "N2", "nta_name": "Neighborhood Two", "borough": "Manhattan"}
            ),
        ),
        SimpleNamespace(
            neighborhood_id="n3",
            neighborhood=SimpleNamespace(
                region_metadata={"nta_code": "N3", "nta_name": "Neighborhood Three", "borough": "Queens"}
            ),
        ),
    ]
    service.service_area_repository.list_for_instructor.return_value = areas

    profile = SimpleNamespace(
        id="profile-1",
        user_id="user-1",
        bio="Bio",
        years_experience=3,
        min_advance_booking_hours=2,
        buffer_time_minutes=0,
        created_at=None,
        updated_at=None,
        services=123,
        user=SimpleNamespace(id="user-1", first_name="Alex", last_name="Smith"),
    )

    result = service._profile_to_dict(profile)

    assert result["services"] == []
    assert result["service_area_summary"].startswith("Brooklyn +")
    assert len(result["service_area_neighborhoods"]) == 3


def test_profile_to_dict_preferred_places_privacy():
    service = _build_service()

    teaching = SimpleNamespace(
        kind="teaching_location",
        address="123 Main St",
        label="Studio",
        position=0,
        approx_lat=40.7,
        approx_lng=-74.0,
        neighborhood="Chelsea",
    )
    public = SimpleNamespace(
        kind="public_space",
        address="Central Park",
        label="Park",
        position=0,
    )

    profile = SimpleNamespace(
        id="profile-1",
        user_id="user-1",
        bio="Bio",
        years_experience=3,
        min_advance_booking_hours=2,
        buffer_time_minutes=0,
        created_at=None,
        updated_at=None,
        services=[],
        user=SimpleNamespace(
            id="user-1",
            first_name="Alex",
            last_name="Smith",
            preferred_places=[teaching, public],
            service_areas=[],
        ),
    )

    result = service._profile_to_dict(profile, include_private_fields=False)

    assert "address" not in result["preferred_teaching_locations"][0]
    assert result["preferred_teaching_locations"][0]["label"] == "Studio"
    assert result["preferred_teaching_locations"][0]["approx_lat"] == pytest.approx(40.7)
    assert result["preferred_public_spaces"][0]["address"] == "Central Park"


def test_invalidate_instructor_caches_no_cache():
    service = _build_service()
    service.cache_service = None
    service._invalidate_instructor_caches("user-1")


def test_get_available_catalog_services_cache_hit_debug(monkeypatch):
    service = _build_service()
    service.cache_service = MagicMock()
    service.cache_service.get.return_value = [{"id": "cached"}]

    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    assert service.get_available_catalog_services() == [{"id": "cached"}]


def test_get_available_catalog_services_category_not_found():
    service = _build_service()
    service.cache_service = MagicMock()
    service.cache_service.get.return_value = None
    service.category_repository.find_one_by.return_value = None

    with pytest.raises(NotFoundException):
        service.get_available_catalog_services(category_slug="missing")


def test_get_available_catalog_services_cache_miss_sets_cache():
    service = _build_service()
    service.cache_service = MagicMock()
    service.cache_service.get.return_value = None
    service.catalog_repository.get_active_services_with_categories.return_value = [
        SimpleNamespace(
            id="svc-1",
            category_id="cat-1",
            category=None,
            name="Yoga",
            slug="yoga",
            description="",
            search_terms=None,
            display_order=1,
            online_capable=True,
            requires_certification=False,
        )
    ]

    result = service.get_available_catalog_services()

    assert result
    service.cache_service.set.assert_called_once()


def test_get_service_categories_cache_hit_and_set():
    service = _build_service()
    service.cache_service = MagicMock()
    service.cache_service.get.return_value = [{"id": "cached"}]
    assert service.get_service_categories() == [{"id": "cached"}]

    service.cache_service.get.return_value = None
    service.category_repository.get_all.return_value = [
        SimpleNamespace(
            id="cat-2",
            name="Music",
            slug="music",
            description="desc",
            display_order=2,
            subtitle=None,
            icon_name=None,
        ),
        SimpleNamespace(
            id="cat-1",
            name="Sports",
            slug="sports",
            description="desc",
            display_order=1,
            subtitle=None,
            icon_name=None,
        ),
    ]

    result = service.get_service_categories()
    assert [c["id"] for c in result] == ["cat-1", "cat-2"]
    service.cache_service.set.assert_called_once()


def test_create_instructor_service_from_catalog_errors_and_success():
    service = _build_service()

    service.profile_repository.find_one_by.return_value = None
    with pytest.raises(NotFoundException):
        service.create_instructor_service_from_catalog("user-1", "cat-1", 60.0)

    profile = SimpleNamespace(id="profile-1")
    service.profile_repository.find_one_by.return_value = profile
    service.catalog_repository.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        service.create_instructor_service_from_catalog("user-1", "cat-1", 60.0)

    catalog = SimpleNamespace(id="cat-1", name="Yoga")
    service.catalog_repository.get_by_id.return_value = catalog
    service.service_repository.find_one_by.return_value = SimpleNamespace(id="svc-1")
    with pytest.raises(BusinessRuleException):
        service.create_instructor_service_from_catalog("user-1", "cat-1", 60.0)

    service.service_repository.find_one_by.return_value = None
    created_service = SimpleNamespace(id="svc-1", service_catalog_id="cat-1")
    service.service_repository.create.return_value = created_service
    service.cache_service = MagicMock()
    service._invalidate_instructor_caches = MagicMock()

    with patch("app.services.instructor_service.invalidate_on_service_change"):
        with patch.object(service, "_instructor_service_to_dict", return_value={"id": "svc-1"}):
            result = service.create_instructor_service_from_catalog("user-1", "cat-1", 60.0)

    assert result == {"id": "svc-1"}
    service._invalidate_instructor_caches.assert_called_once_with("user-1")


def test_search_services_semantic_filters_and_breaks():
    service = _build_service()
    service._catalog_service_to_dict = MagicMock(return_value={"id": "svc"})
    service._get_service_analytics = MagicMock(return_value={})

    svc_wrong = SimpleNamespace(id="svc-1", category_id=2, online_capable=True)
    svc_right = SimpleNamespace(id="svc-2", category_id=1, online_capable=True)
    svc_skip_online = SimpleNamespace(id="svc-3", category_id=1, online_capable=False)

    service.catalog_repository.find_similar_by_embedding.return_value = [
        (svc_wrong, 0.9),
        (svc_right, 0.8),
        (svc_skip_online, 0.7),
    ]

    results = service.search_services_semantic(
        query_embedding=[0.1] * 3, category_id=1, online_capable=True, limit=1
    )

    assert len(results) == 1


def test_get_popular_services_builds_results():
    service = _build_service()

    analytics = SimpleNamespace(to_dict=lambda: {"metric": 1})
    service.catalog_repository.get_popular_services.return_value = [
        {"service": SimpleNamespace(id="svc-1"), "analytics": analytics, "popularity_score": 9.5}
    ]
    service._catalog_service_to_dict = MagicMock(return_value={"id": "svc-1"})

    results = service.get_popular_services(limit=1, days=7)

    assert results[0]["analytics"] == {"metric": 1}
    assert results[0]["popularity_score"] == 9.5


def test_search_services_enhanced_tracks_analytics_and_price_range():
    service = _build_service()
    svc = SimpleNamespace(id="svc-1")
    service.catalog_repository.search_services.return_value = [svc]
    service._catalog_service_to_dict = MagicMock(return_value={"id": "svc-1"})
    service._get_instructors_for_service_in_price_range = MagicMock(
        return_value=[SimpleNamespace(hourly_rate=75)]
    )
    service._calculate_price_range = MagicMock(return_value={"min": 75, "max": 75})

    results = service.search_services_enhanced(
        query_text="python", min_price=50, max_price=100, limit=10
    )

    assert results["services"][0]["matching_instructors"] == 1
    assert results["services"][0]["actual_price_range"] == {"min": 75, "max": 75}
    service.analytics_repository.increment_search_count.assert_called_once_with("svc-1")


def test_get_instructors_for_service_in_price_range_filters():
    service = _build_service()
    service.service_repository.find_by.return_value = [
        SimpleNamespace(hourly_rate=40),
        SimpleNamespace(hourly_rate=60),
        SimpleNamespace(hourly_rate=120),
    ]

    results = service._get_instructors_for_service_in_price_range("svc-1", 50, 100)

    assert [s.hourly_rate for s in results] == [60]


def test_get_top_services_per_category_cache_hit_and_set():
    service = _build_service()
    service.cache_service = MagicMock()
    service.cache_service.get.return_value = {"cached": True}
    assert service.get_top_services_per_category(limit=1) == {"cached": True}

    service.cache_service.get.return_value = None
    category = SimpleNamespace(id="cat-1", name="Music", slug="music", icon_name=None, display_order=1)
    service.category_repository.get_all.return_value = [category]
    service.catalog_repository.get_active_services_with_categories.return_value = [
        SimpleNamespace(id="svc-1", name="Piano", slug="piano", display_order=1)
    ]
    service.analytics_repository.get_or_create.return_value = SimpleNamespace(
        active_instructors=1, demand_score=5, is_trending=False
    )

    result = service.get_top_services_per_category(limit=1)
    assert result["categories"]
    service.cache_service.set.assert_called_once()


def test_get_kids_available_services_cache_hit_and_set():
    service = _build_service()
    service.cache_service = MagicMock()
    service.cache_service.get.return_value = [{"id": "cached"}]
    assert service.get_kids_available_services() == [{"id": "cached"}]

    service.cache_service.get.return_value = None
    service.catalog_repository.get_services_available_for_kids_minimal.return_value = [
        {"id": "svc-1"}
    ]
    assert service.get_kids_available_services() == [{"id": "svc-1"}]
    service.cache_service.set.assert_called_once()


def test_get_instructor_service_dependency_injection():
    db = MagicMock()
    cache_service = MagicMock()
    service = get_instructor_service(db, cache_service)

    assert isinstance(service, InstructorService)
    assert service.cache_service is cache_service
