from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.repositories.mcp_instructor_repository import (
    MCPInstructorRepository,
    _build_status_filters,
)


def _get_service_by_slug(db, slug: str) -> ServiceCatalog:
    service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == slug).first()
    if service:
        return service
    category = db.query(ServiceCategory).first()
    if not category:
        category = ServiceCategory(name="Test Category")
        db.add(category)
        db.flush()
    subcategory = db.query(ServiceSubcategory).filter(
        ServiceSubcategory.category_id == category.id
    ).first()
    if not subcategory:
        subcategory = ServiceSubcategory(name="Test Subcategory", category_id=category.id, display_order=1)
        db.add(subcategory)
        db.flush()
    service = ServiceCatalog(name=slug.title(), slug=slug, subcategory_id=subcategory.id)
    db.add(service)
    db.flush()
    return service


def test_list_instructors_filters_and_cursor(db, test_instructor, test_instructor_2):
    repo = MCPInstructorRepository(db)

    profile_2 = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor_2.id)
        .first()
    )
    assert profile_2 is not None
    profile_2.is_live = False
    profile_2.onboarding_completed_at = None
    profile_2.skills_configured = False
    profile_2.bgc_status = None
    piano = _get_service_by_slug(db, "piano")
    db.add(
        Service(
            instructor_profile_id=profile_2.id,
            service_catalog_id=piano.id,
            hourly_rate=55.0,
            is_active=True,
        )
    )
    db.flush()

    profiles, next_cursor = repo.list_instructors(
        status="registered",
        is_founding=None,
        service_slug=None,
        category_name=None,
        limit=50,
        cursor=None,
    )
    ids = {profile.user_id for profile in profiles}
    assert test_instructor_2.id in ids

    profiles, next_cursor = repo.list_instructors(
        status=None,
        is_founding=None,
        service_slug="piano",
        category_name=None,
        limit=1,
        cursor=None,
    )
    assert len(profiles) == 1
    assert profiles[0].user_id == test_instructor.id
    assert next_cursor is not None

    profiles_next, _next = repo.list_instructors(
        status=None,
        is_founding=None,
        service_slug=None,
        category_name=None,
        limit=1,
        cursor=next_cursor,
    )
    assert profiles_next


def test_get_service_coverage(db, test_instructor, test_instructor_2):
    repo = MCPInstructorRepository(db)

    yoga = _get_service_by_slug(db, "yoga")
    profile_2 = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor_2.id)
        .first()
    )
    assert profile_2 is not None
    db.add(
        Service(
            instructor_profile_id=profile_2.id,
            service_catalog_id=yoga.id,
            hourly_rate=60.0,
            is_active=True,
        )
    )
    db.flush()

    coverage = repo.get_service_coverage(status="live", group_by="category", top=10)
    assert coverage["total_instructors"] >= 1
    assert coverage["labels"]
    assert coverage["values"]


def test_get_instructor_by_identifier(db, test_instructor):
    repo = MCPInstructorRepository(db)

    profile = repo.get_instructor_by_identifier(test_instructor.id)
    assert profile is not None
    assert profile.user_id == test_instructor.id

    profile_email = repo.get_instructor_by_identifier(test_instructor.email)
    assert profile_email is not None
    assert profile_email.user_id == test_instructor.id

    test_instructor.first_name = f"Unique{test_instructor.id[-4:]}"
    test_instructor.last_name = f"Name{test_instructor.id[-6:]}"
    db.flush()
    full_name = f"{test_instructor.first_name} {test_instructor.last_name}"
    profile_name = repo.get_instructor_by_identifier(full_name)
    assert profile_name is not None
    assert profile_name.user_id == test_instructor.id


def test_name_search_escapes_like_patterns(db, test_instructor):
    repo = MCPInstructorRepository(db)

    test_instructor.first_name = "test"
    test_instructor.last_name = "pattern"
    db.flush()

    result = repo.get_instructor_by_identifier("test%pattern")
    assert result is None

    result = repo.get_instructor_by_identifier("test_pattern")
    assert result is None


def test_list_instructors_filters_by_category_name(db, test_instructor):
    repo = MCPInstructorRepository(db)

    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    )
    assert profile is not None
    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active.is_(True))
        .order_by(Service.id)
        .first()
    )
    assert service is not None
    category_name = service.catalog_entry.subcategory.category.name

    profiles, _ = repo.list_instructors(
        status=None,
        is_founding=None,
        service_slug=None,
        category_name=category_name,
        limit=10,
        cursor=None,
    )

    assert any(p.user_id == test_instructor.id for p in profiles)


def test_status_filter_variants_cover_all_supported_statuses():
    assert _build_status_filters("live")
    assert _build_status_filters("paused")
    assert _build_status_filters("onboarding")
    assert _build_status_filters("registered")
    assert _build_status_filters("unknown-status") == []


def test_get_instructor_by_identifier_blank_and_profile_id(db, test_instructor):
    repo = MCPInstructorRepository(db)
    assert repo.get_instructor_by_identifier("   ") is None

    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()
    )
    assert profile is not None
    # Exercises fallback lookup by InstructorProfile.id after User.id lookup misses.
    result = repo.get_instructor_by_identifier(profile.id)
    assert result is not None
    assert result.id == profile.id


def test_get_instructor_by_identifier_email_miss_falls_back(db):
    repo = MCPInstructorRepository(db)
    assert repo.get_instructor_by_identifier("missing@example.com") is None


def test_get_service_coverage_without_status_filters(db):
    repo = MCPInstructorRepository(db)
    coverage = repo.get_service_coverage(status="", group_by="service", top=5)
    assert "labels" in coverage
    assert "values" in coverage


def test_get_booking_and_review_stats_empty_row_paths(monkeypatch):
    class _DummyQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

        def all(self):
            return [("inst-1", None, 0)]

        def group_by(self, *_args, **_kwargs):
            return self

    class _DummyDB:
        def query(self, *_args, **_kwargs):
            return _DummyQuery()

    repo = MCPInstructorRepository(_DummyDB())

    stats = repo.get_booking_stats("inst-1")
    assert stats == {"completed": 0, "cancelled": 0, "no_show": 0}

    single = repo.get_review_stats_for_user("inst-1")
    assert single == {"rating_avg": 0.0, "rating_count": 0}

    many = repo.get_review_stats(["inst-1"])
    assert many["inst-1"]["rating_avg"] == 0.0
    assert many["inst-1"]["rating_count"] == 0
