from __future__ import annotations

from fastapi import HTTPException
import pytest

from app.routes.v1 import favorites as favorites_routes


class _FavoritesServiceStub:
    def __init__(self, *, result=None, favorites=None):
        self._result = result or {"success": True, "message": "ok"}
        self._favorites = favorites or []

    def add_favorite(self, *args, **kwargs):
        return self._result

    def remove_favorite(self, *args, **kwargs):
        return self._result

    def get_student_favorites(self, *args, **kwargs):
        return self._favorites

    def is_favorited(self, *args, **kwargs):
        return True


@pytest.mark.asyncio
async def test_add_favorite_handles_value_error(monkeypatch, test_student):
    async def _boom(*_args, **_kwargs):
        raise ValueError("bad input")

    monkeypatch.setattr("app.routes.v1.favorites.asyncio.to_thread", _boom)

    with pytest.raises(HTTPException) as exc:
        await favorites_routes.add_favorite(
            instructor_id="01HF4G12ABCDEF3456789XYZAB",
            current_user=test_student,
            favorites_service=_FavoritesServiceStub(),
            _=None,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_remove_favorite_handles_unexpected_error(monkeypatch, test_student):
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routes.v1.favorites.asyncio.to_thread", _boom)
    monkeypatch.setattr("app.routes.v1.favorites.raise_503_if_pool_exhaustion", lambda *_: None)

    with pytest.raises(HTTPException) as exc:
        await favorites_routes.remove_favorite(
            instructor_id="01HF4G12ABCDEF3456789XYZAB",
            current_user=test_student,
            favorites_service=_FavoritesServiceStub(),
            _=None,
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_remove_favorite_handles_value_error(monkeypatch, test_student):
    async def _boom(*_args, **_kwargs):
        raise ValueError("bad remove")

    monkeypatch.setattr("app.routes.v1.favorites.asyncio.to_thread", _boom)

    with pytest.raises(HTTPException) as exc:
        await favorites_routes.remove_favorite(
            instructor_id="01HF4G12ABCDEF3456789XYZAB",
            current_user=test_student,
            favorites_service=_FavoritesServiceStub(),
            _=None,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_favorites_builds_profiles(monkeypatch, test_student, test_instructor):
    async def _call(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("app.routes.v1.favorites.asyncio.to_thread", _call)

    service = _FavoritesServiceStub(favorites=[test_instructor])
    response = await favorites_routes.get_favorites(
        current_user=test_student,
        favorites_service=service,
    )
    assert response.total == 1
    assert response.favorites[0].id == test_instructor.id
    assert response.favorites[0].profile is not None


@pytest.mark.asyncio
async def test_get_favorites_handles_error(monkeypatch, test_student):
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routes.v1.favorites.asyncio.to_thread", _boom)
    monkeypatch.setattr("app.routes.v1.favorites.raise_503_if_pool_exhaustion", lambda *_: None)

    with pytest.raises(HTTPException) as exc:
        await favorites_routes.get_favorites(
            current_user=test_student,
            favorites_service=_FavoritesServiceStub(),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_check_favorite_status_handles_error(monkeypatch, test_student):
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routes.v1.favorites.asyncio.to_thread", _boom)
    monkeypatch.setattr("app.routes.v1.favorites.raise_503_if_pool_exhaustion", lambda *_: None)

    with pytest.raises(HTTPException) as exc:
        await favorites_routes.check_favorite_status(
            instructor_id="01HF4G12ABCDEF3456789XYZAB",
            current_user=test_student,
            favorites_service=_FavoritesServiceStub(),
        )
    assert exc.value.status_code == 500
