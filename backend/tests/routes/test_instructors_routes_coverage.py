from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.core.exceptions import BusinessRuleException, DomainException, NotFoundException
from app.core.ulid_helper import generate_ulid
from app.routes.v1 import instructors as instructors_routes
from app.schemas.instructor import InstructorProfileCreate, InstructorProfileUpdate
from app.services.address_service import AddressService


def _profile_payload(*, user_id: str, profile_id: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": profile_id,
        "user_id": user_id,
        "bio": "Bio for instructor profile",
        "years_experience": 4,
        "created_at": now,
        "updated_at": None,
        "min_advance_booking_hours": 2,
        "buffer_time_minutes": 0,
        "user": {
            "id": user_id,
            "first_name": "Taylor",
            "last_name": "Smith",
            "last_initial": "S",
        },
        "services": [
            {
                "id": "service-1",
                "service_catalog_id": "catalog-1",
                "hourly_rate": 85,
                "service_catalog_name": "Piano lessons",
            }
        ],
    }


def _profile_object(*, user_id: str, profile_id: str) -> SimpleNamespace:
    payload = _profile_payload(user_id=user_id, profile_id=profile_id)
    user = SimpleNamespace(**payload["user"])
    services = [SimpleNamespace(**svc) for svc in payload["services"]]
    payload = {**payload, "user": user, "services": services}
    return SimpleNamespace(**payload)


class _InstructorServiceStub:
    def __init__(self):
        self.cache_service = None

    def create_instructor_profile(self, *_args, **_kwargs):
        raise Exception("already exists")

    def get_instructor_profile(self, *_args, **_kwargs):
        raise Exception("not found")

    def update_instructor_profile(self, *_args, **_kwargs):
        raise DomainException("bad update")

    def go_live(self, *_args, **_kwargs):
        raise BusinessRuleException("missing prereqs")

    def delete_instructor_profile(self, *_args, **_kwargs):
        raise Exception("not found")

    def get_public_instructor_profile(self, *_args, **_kwargs):
        return _profile_payload(user_id="user-1", profile_id="profile-1")

    def get_instructor_user(self, *_args, **_kwargs):
        raise Exception("missing")


class _FavoritesServiceStub:
    def is_favorited(self, *_args, **_kwargs):
        return False

    def get_instructor_favorite_stats(self, *_args, **_kwargs):
        return {"favorite_count": 2}


class _AddressServiceStub:
    def get_coverage_geojson_for_instructors(self, *_args, **_kwargs):
        return {"type": "FeatureCollection", "features": []}


class _InstructorServiceListStub:
    def __init__(self, payload):
        self._payload = payload
        self.last_kwargs = None

    def get_instructors_filtered(self, *_args, **kwargs):
        self.last_kwargs = kwargs
        return self._payload


def test_get_address_service_returns_service(db):
    service = instructors_routes.get_address_service(db)
    assert isinstance(service, AddressService)
    assert service.db is db


@pytest.mark.asyncio
async def test_create_profile_handles_existing_profile(test_instructor):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.create_profile(
            profile=InstructorProfileCreate(
                bio="Bio long enough",
                years_experience=2,
                services=[
                    {
                        "service_catalog_id": "catalog-1",
                        "hourly_rate": 50,
                    }
                ],
            ),
            current_user=test_instructor,
            instructor_service=_InstructorServiceStub(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_my_profile_requires_instructor(test_student):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.get_my_profile(
            current_user=test_student,
            instructor_service=_InstructorServiceStub(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_my_profile_not_found(test_instructor):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.get_my_profile(
            current_user=test_instructor,
            instructor_service=_InstructorServiceStub(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_my_profile_returns_dict_payload(test_instructor):
    service = _InstructorServiceStub()
    service.get_instructor_profile = lambda *_args, **_kwargs: _profile_payload(
        user_id=test_instructor.id,
        profile_id="profile-1",
    )

    response = await instructors_routes.get_my_profile(
        current_user=test_instructor,
        instructor_service=service,
    )
    assert response.id == "profile-1"


@pytest.mark.asyncio
async def test_get_my_profile_returns_orm_payload(test_instructor):
    service = _InstructorServiceStub()
    service.get_instructor_profile = lambda *_args, **_kwargs: _profile_object(
        user_id=test_instructor.id,
        profile_id="profile-2",
    )

    response = await instructors_routes.get_my_profile(
        current_user=test_instructor,
        instructor_service=service,
    )
    assert response.id == "profile-2"


@pytest.mark.asyncio
async def test_get_my_profile_raises_unexpected_error(test_instructor):
    service = _InstructorServiceStub()
    service.get_instructor_profile = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        Exception("boom")
    )

    with pytest.raises(Exception, match="boom"):
        await instructors_routes.get_my_profile(
            current_user=test_instructor,
            instructor_service=service,
        )


@pytest.mark.asyncio
async def test_update_profile_requires_instructor(test_student):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.update_profile(
            profile_update=InstructorProfileUpdate(),
            current_user=test_student,
            instructor_service=_InstructorServiceStub(),
            cache_service=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_profile_domain_exception(test_instructor):
    service = _InstructorServiceStub()
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.update_profile(
            profile_update=InstructorProfileUpdate(),
            current_user=test_instructor,
            instructor_service=service,
            cache_service=SimpleNamespace(),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_update_profile_not_found(test_instructor):
    service = _InstructorServiceStub()
    service.update_instructor_profile = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        Exception("not found")
    )

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.update_profile(
            profile_update=InstructorProfileUpdate(),
            current_user=test_instructor,
            instructor_service=service,
            cache_service=None,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_profile_success_dict(test_instructor):
    service = _InstructorServiceStub()
    service.update_instructor_profile = lambda *_args, **_kwargs: _profile_payload(
        user_id=test_instructor.id,
        profile_id="profile-1",
    )

    response = await instructors_routes.update_profile(
        profile_update=InstructorProfileUpdate(),
        current_user=test_instructor,
        instructor_service=service,
        cache_service=SimpleNamespace(),
    )
    assert response.id == "profile-1"


@pytest.mark.asyncio
async def test_list_instructors_invalid_filter():
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.list_instructors(
            service_catalog_id="catalog-1",
            min_price=200,
            max_price=50,
            age_group=None,
            page=1,
            per_page=20,
            instructor_service=_InstructorServiceListStub({}),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_instructors_returns_paginated():
    payload = _profile_payload(user_id="user-1", profile_id="profile-1")
    result = {
        "instructors": [SimpleNamespace(**payload), payload],
        "metadata": {"total_found": 2},
    }
    service = _InstructorServiceListStub(result)

    response = await instructors_routes.list_instructors(
        service_catalog_id="catalog-1",
        min_price=None,
        max_price=None,
        age_group=None,
        page=1,
        per_page=1,
        instructor_service=service,
    )

    assert response.total == 2
    assert response.page == 1
    assert response.per_page == 1
    assert response.has_next is True
    assert len(response.items) == 2


@pytest.mark.asyncio
async def test_list_instructors_forwards_taxonomy_filters():
    result = {
        "instructors": [],
        "metadata": {"total_found": 0},
    }
    service = _InstructorServiceListStub(result)

    await instructors_routes.list_instructors(
        service_catalog_id="catalog-1",
        min_price=None,
        max_price=None,
        age_group=None,
        skill_level="beginner,intermediate,beginner",
        subcategory_id="01HABCDEFGHJKMNPQRSTVWXYZ0",
        content_filters="goal:enrichment|format:one_time|style:jazz|grade_level:6th,7th",
        page=1,
        per_page=20,
        instructor_service=service,
    )

    assert service.last_kwargs is not None
    assert service.last_kwargs["taxonomy_filter_selections"] == {
        "skill_level": ["beginner", "intermediate"],
        "goal": ["enrichment"],
        "format": ["one_time"],
        "style": ["jazz"],
        "grade_level": ["6th", "7th"],
    }
    assert service.last_kwargs["subcategory_id"] == "01HABCDEFGHJKMNPQRSTVWXYZ0"


@pytest.mark.asyncio
async def test_list_instructors_rejects_invalid_skill_level():
    service = _InstructorServiceListStub({"instructors": [], "metadata": {"total_found": 0}})

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.list_instructors(
            service_catalog_id="catalog-1",
            min_price=None,
            max_price=None,
            age_group=None,
            skill_level="expert",
            subcategory_id=None,
            content_filters=None,
            page=1,
            per_page=20,
            instructor_service=service,
        )

    assert exc.value.status_code == 400
    assert "Invalid skill_level" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_instructors_rejects_malformed_content_filter_segments():
    result = {"instructors": [], "metadata": {"total_found": 0}}
    service = _InstructorServiceListStub(result)

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.list_instructors(
            service_catalog_id="catalog-1",
            min_price=None,
            max_price=None,
            age_group=None,
            skill_level=None,
            subcategory_id=None,
            content_filters="goal:enrichment|broken|:missing_key|format:",
            page=1,
            per_page=20,
            instructor_service=service,
        )

    assert exc.value.status_code == 400
    assert "Malformed content_filters segment" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_instructors_skill_level_param_overrides_content_filters_skill_level():
    result = {"instructors": [], "metadata": {"total_found": 0}}
    service = _InstructorServiceListStub(result)

    await instructors_routes.list_instructors(
        service_catalog_id="catalog-1",
        min_price=None,
        max_price=None,
        age_group=None,
        skill_level="advanced",
        subcategory_id=None,
        content_filters="skill_level:beginner,intermediate|goal:enrichment",
        page=1,
        per_page=20,
        instructor_service=service,
    )

    assert service.last_kwargs is not None
    assert service.last_kwargs["taxonomy_filter_selections"] == {
        "skill_level": ["advanced"],
        "goal": ["enrichment"],
    }


@pytest.mark.asyncio
async def test_list_instructors_rejects_content_filters_with_too_many_keys():
    service = _InstructorServiceListStub({"instructors": [], "metadata": {"total_found": 0}})

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.list_instructors(
            service_catalog_id="catalog-1",
            min_price=None,
            max_price=None,
            age_group=None,
            skill_level=None,
            subcategory_id=None,
            content_filters="|".join(f"k{i}:v" for i in range(11)),
            page=1,
            per_page=20,
            instructor_service=service,
        )

    assert exc.value.status_code == 400
    assert "at most 10 keys" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_instructors_rejects_content_filters_with_too_many_values_for_key():
    service = _InstructorServiceListStub({"instructors": [], "metadata": {"total_found": 0}})
    too_many_values = ",".join(f"v{i}" for i in range(21))

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.list_instructors(
            service_catalog_id="catalog-1",
            min_price=None,
            max_price=None,
            age_group=None,
            skill_level=None,
            subcategory_id=None,
            content_filters=f"goal:{too_many_values}",
            page=1,
            per_page=20,
            instructor_service=service,
        )

    assert exc.value.status_code == 400
    assert "at most 20 values" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_go_live_business_rule_exception(test_instructor):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.go_live(
            current_user=test_instructor,
            instructor_service=_InstructorServiceStub(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_go_live_requires_instructor(test_student):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.go_live(
            current_user=test_student,
            instructor_service=_InstructorServiceStub(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_go_live_not_found_exception(test_instructor):
    service = _InstructorServiceStub()
    service.go_live = lambda *_args, **_kwargs: (_ for _ in ()).throw(NotFoundException("missing"))

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.go_live(
            current_user=test_instructor,
            instructor_service=service,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_go_live_success(test_instructor):
    service = _InstructorServiceStub()
    service.go_live = lambda *_args, **_kwargs: _profile_object(
        user_id=test_instructor.id,
        profile_id="profile-3",
    )

    response = await instructors_routes.go_live(
        current_user=test_instructor,
        instructor_service=service,
    )
    assert response.id == "profile-3"


@pytest.mark.asyncio
async def test_delete_profile_requires_instructor(test_student):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.delete_profile(
            current_user=test_student,
            instructor_service=_InstructorServiceStub(),
            cache_service=None,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_profile_not_found(test_instructor):
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.delete_profile(
            current_user=test_instructor,
            instructor_service=_InstructorServiceStub(),
            cache_service=None,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile_assigns_cache_service(test_instructor):
    service = _InstructorServiceStub()
    service.delete_instructor_profile = lambda *_args, **_kwargs: None
    cache = SimpleNamespace()

    await instructors_routes.delete_profile(
        current_user=test_instructor,
        instructor_service=service,
        cache_service=cache,
    )
    assert service.cache_service is cache


@pytest.mark.asyncio
async def test_delete_profile_raises_unexpected(test_instructor):
    service = _InstructorServiceStub()
    service.delete_instructor_profile = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        Exception("boom")
    )

    with pytest.raises(Exception, match="boom"):
        await instructors_routes.delete_profile(
            current_user=test_instructor,
            instructor_service=service,
            cache_service=None,
        )


@pytest.mark.asyncio
async def test_get_instructor_sets_favorite_counts(test_student):
    service = _InstructorServiceStub()
    favorites = _FavoritesServiceStub()
    response = await instructors_routes.get_instructor(
        instructor_id="01HF4G12ABCDEF3456789XYZAB",
        response=SimpleNamespace(headers={}),
        instructor_service=service,
        favorites_service=favorites,
        current_user=None,
    )
    assert response.favorited_count == 2
    assert response.is_favorited is None


@pytest.mark.asyncio
async def test_get_instructor_sets_favorite_flag(test_student):
    service = _InstructorServiceStub()
    favorites = _FavoritesServiceStub()
    response = await instructors_routes.get_instructor(
        instructor_id="01HF4G12ABCDEF3456789XYZAB",
        response=SimpleNamespace(headers={}),
        instructor_service=service,
        favorites_service=favorites,
        current_user=test_student,
    )
    assert response.is_favorited is False


@pytest.mark.asyncio
async def test_get_instructor_handles_not_found(test_student):
    service = _InstructorServiceStub()
    service.get_public_instructor_profile = lambda *_args, **_kwargs: None

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.get_instructor(
            instructor_id="01HF4G12ABCDEF3456789XYZAB",
            response=SimpleNamespace(headers={}),
            instructor_service=service,
            favorites_service=_FavoritesServiceStub(),
            current_user=test_student,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_instructor_handles_exception(monkeypatch, test_student):
    service = _InstructorServiceStub()
    service.get_public_instructor_profile = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        Exception("not found")
    )
    monkeypatch.setattr("app.routes.v1.instructors.raise_503_if_pool_exhaustion", lambda *_: None)

    with pytest.raises(HTTPException) as exc:
        await instructors_routes.get_instructor(
            instructor_id="01HF4G12ABCDEF3456789XYZAB",
            response=SimpleNamespace(headers={}),
            instructor_service=service,
            favorites_service=_FavoritesServiceStub(),
            current_user=test_student,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_coverage_invalid_ulid():
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.get_coverage(
            instructor_id="bad-id",
            address_service=_AddressServiceStub(),
            instructor_service=_InstructorServiceStub(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_coverage_instructor_not_found():
    with pytest.raises(HTTPException) as exc:
        await instructors_routes.get_coverage(
            instructor_id=generate_ulid(),
            address_service=_AddressServiceStub(),
            instructor_service=_InstructorServiceStub(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_coverage_success():
    instructor_user = SimpleNamespace(id="user-1")
    service = _InstructorServiceStub()
    service.get_instructor_user = lambda *_args, **_kwargs: instructor_user

    response = await instructors_routes.get_coverage(
        instructor_id=generate_ulid(),
        address_service=_AddressServiceStub(),
        instructor_service=service,
    )
    assert response.type == "FeatureCollection"
