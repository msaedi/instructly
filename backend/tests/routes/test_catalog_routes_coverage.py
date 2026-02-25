"""Coverage tests for catalog routes — DomainException → to_http_exception() path."""

from __future__ import annotations

from fastapi import HTTPException
import pytest

from app.core.exceptions import DomainException, NotFoundException
from app.routes.v1 import catalog as routes


class _FailingService:
    """Service stub that raises DomainException on every call."""

    def __init__(self, exc: DomainException):
        self._exc = exc

    def list_categories(self):
        raise self._exc

    def get_category(self, _slug: str):
        raise self._exc

    def get_subcategory(self, _cat: str, _sub: str):
        raise self._exc

    def get_service(self, _service_id: str):
        raise self._exc

    def list_services_for_subcategory(self, _sub_id: str):
        raise self._exc

    def get_filters_for_subcategory(self, _sub_id: str):
        raise self._exc


class _FakeResponse:
    def __init__(self):
        self.headers = {}


# ---- L49-50: DomainException in list_categories ----
@pytest.mark.asyncio
async def test_list_categories_domain_exception():
    service = _FailingService(NotFoundException("Category not found"))

    with pytest.raises(HTTPException) as exc:
        await routes.list_categories(
            response=_FakeResponse(),
            service=service,
        )
    assert exc.value.status_code == 404


# ---- DomainException in get_category ----
@pytest.mark.asyncio
async def test_get_category_domain_exception():
    service = _FailingService(DomainException("Something went wrong"))

    with pytest.raises(HTTPException) as exc:
        await routes.get_category(
            response=_FakeResponse(),
            category_slug="music",
            service=service,
        )
    assert exc.value.status_code == 500


# ---- DomainException in get_subcategory ----
@pytest.mark.asyncio
async def test_get_subcategory_domain_exception():
    service = _FailingService(NotFoundException("Subcategory missing"))

    with pytest.raises(HTTPException) as exc:
        await routes.get_subcategory(
            response=_FakeResponse(),
            category_slug="music",
            subcategory_slug="piano",
            service=service,
        )
    assert exc.value.status_code == 404


# ---- DomainException in get_service ----
@pytest.mark.asyncio
async def test_get_service_domain_exception():
    service = _FailingService(NotFoundException("Service not found"))

    with pytest.raises(HTTPException) as exc:
        await routes.get_service(
            response=_FakeResponse(),
            service_id="01ABCDEFGHIJKLMNOPQRSTUVWX",
            service=service,
        )
    assert exc.value.status_code == 404


# ---- DomainException in list_services_for_subcategory ----
@pytest.mark.asyncio
async def test_list_services_domain_exception():
    service = _FailingService(DomainException("Error"))

    with pytest.raises(HTTPException) as exc:
        await routes.list_services_for_subcategory(
            response=_FakeResponse(),
            subcategory_id="01ABCDEFGHIJKLMNOPQRSTUVWX",
            service=service,
        )
    assert exc.value.status_code == 500


# ---- DomainException in get_subcategory_filters ----
@pytest.mark.asyncio
async def test_get_subcategory_filters_domain_exception():
    service = _FailingService(DomainException("Filters error"))

    with pytest.raises(HTTPException) as exc:
        await routes.get_subcategory_filters(
            response=_FakeResponse(),
            subcategory_id="01ABCDEFGHIJKLMNOPQRSTUVWX",
            service=service,
        )
    assert exc.value.status_code == 500
