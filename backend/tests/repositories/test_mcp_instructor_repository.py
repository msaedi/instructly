from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.repositories.mcp_instructor_repository import MCPInstructorRepository


def _get_service_by_slug(db, slug: str) -> ServiceCatalog:
    service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == slug).first()
    if service:
        return service
    category = db.query(ServiceCategory).first()
    if not category:
        category = ServiceCategory(name="Test Category", slug="test-category")
        db.add(category)
        db.flush()
    service = ServiceCatalog(name=slug.title(), slug=slug, category_id=category.id)
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
        category_slug=None,
        limit=50,
        cursor=None,
    )
    ids = {profile.user_id for profile in profiles}
    assert test_instructor_2.id in ids

    profiles, next_cursor = repo.list_instructors(
        status=None,
        is_founding=None,
        service_slug="piano",
        category_slug=None,
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
        category_slug=None,
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
