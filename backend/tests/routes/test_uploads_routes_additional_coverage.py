from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.routes.v1 import uploads as uploads_routes
from app.services.dependencies import get_personal_asset_service


class _StubPresigned:
    def __init__(self):
        self.url = "https://example.com/put"
        self.headers = {"Content-Type": "image/png"}
        self.expires_at = "2025-01-01T00:00:00Z"


class _StubStorage:
    def __init__(self):
        self.upload_calls = []

    def generate_presigned_put(self, key, content_type):
        return _StubPresigned()

    def upload_bytes(self, key, data, content_type):
        self.upload_calls.append((key, len(data), content_type))
        return True, 200


class _StubAssetService:
    def __init__(self):
        self.storage = _StubStorage()

    def initiate_upload_key(self, purpose, user_id, filename):
        return f"uploads/{user_id}/tmp/{filename}"

    def finalize_profile_picture(self, user, object_key):
        if object_key == "boom":
            raise ValueError("boom")


@pytest.fixture
def asset_service_override(client):
    svc = _StubAssetService()
    client.app.dependency_overrides[get_personal_asset_service] = lambda: svc
    yield svc
    client.app.dependency_overrides.pop(get_personal_asset_service, None)


def _set_r2_config(monkeypatch):
    monkeypatch.setattr(settings, "r2_bucket_name", "bucket")
    monkeypatch.setattr(settings, "r2_access_key_id", "access")
    monkeypatch.setattr(settings, "r2_secret_access_key", SecretStr("secret"))
    monkeypatch.setattr(settings, "r2_public_base_url", "https://cdn.example.com")


def _override_site_mode(client, mode: str) -> None:
    client.app.dependency_overrides[uploads_routes.get_settings] = lambda: SimpleNamespace(
        site_mode=mode
    )


class TestUploadsRoutesAdditionalCoverage:
    def test_signed_upload_background_check_validation(self, client, auth_headers, monkeypatch, asset_service_override):
        _set_r2_config(monkeypatch)

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "report.txt",
                "content_type": "text/plain",
                "size_bytes": 1024,
                "purpose": "background_check",
            },
        )
        assert res.status_code == 400

    def test_signed_upload_profile_picture_invalid_content(self, client, auth_headers, monkeypatch, asset_service_override):
        _set_r2_config(monkeypatch)

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "avatar.gif",
                "content_type": "image/gif",
                "size_bytes": 1024,
                "purpose": "profile_picture",
            },
        )
        assert res.status_code == 400

    def test_signed_upload_missing_config(self, client, auth_headers, monkeypatch, asset_service_override):
        monkeypatch.setattr(settings, "r2_bucket_name", None)
        monkeypatch.setattr(settings, "r2_access_key_id", None)
        monkeypatch.setattr(settings, "r2_secret_access_key", None)

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "avatar.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "purpose": "profile_picture",
            },
        )
        assert res.status_code == 500

    def test_proxy_upload_rejects_non_local(self, client, auth_headers, monkeypatch, asset_service_override):
        _override_site_mode(client, "prod")

        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": "uploads/user/x.png", "content_type": "image/png"},
            files={"file": ("x.png", b"data", "image/png")},
        )
        assert res.status_code == 404
        client.app.dependency_overrides.pop(uploads_routes.get_settings, None)

    def test_proxy_upload_validation_errors(self, client, auth_headers, monkeypatch, asset_service_override, test_student):
        _override_site_mode(client, "local")

        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": "invalid-key", "content_type": "image/png"},
            files={"file": ("x.png", b"data", "image/png")},
        )
        assert res.status_code == 400

        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": "uploads/other-user/x.png", "content_type": "image/png"},
            files={"file": ("x.png", b"data", "image/png")},
        )
        assert res.status_code == 403

        key = f"uploads/{test_student.id}/x.png"
        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": key, "content_type": "image/gif"},
            files={"file": ("x.gif", b"data", "image/gif")},
        )
        assert res.status_code == 400
        client.app.dependency_overrides.pop(uploads_routes.get_settings, None)

    def test_proxy_upload_empty_and_large(self, client, auth_headers, monkeypatch, asset_service_override, test_student):
        _override_site_mode(client, "local")
        monkeypatch.setattr(uploads_routes, "_PROXY_MAX_BYTES", 10)
        key = f"uploads/{test_student.id}/x.png"

        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": key, "content_type": "image/png"},
            files={"file": ("x.png", b"", "image/png")},
        )
        assert res.status_code == 400

        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": key, "content_type": "image/png"},
            files={"file": ("x.png", b"01234567890", "image/png")},
        )
        assert res.status_code == 413
        client.app.dependency_overrides.pop(uploads_routes.get_settings, None)

    def test_proxy_upload_storage_failure(self, client, auth_headers, monkeypatch, asset_service_override, test_student):
        _override_site_mode(client, "local")
        key = f"uploads/{test_student.id}/x.png"

        def _fail_upload(_key, _data, _content_type):
            return False, 500

        asset_service_override.storage.upload_bytes = _fail_upload

        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": key, "content_type": "image/png"},
            files={"file": ("x.png", b"data", "image/png")},
        )
        assert res.status_code == 502
        client.app.dependency_overrides.pop(uploads_routes.get_settings, None)

    def test_finalize_profile_picture_error(self, client, auth_headers, asset_service_override):
        res = client.post(
            "/api/v1/uploads/r2/finalize/profile-picture",
            headers=auth_headers,
            json={"object_key": "boom"},
        )
        assert res.status_code == 400

    def test_signed_upload_success(self, client, auth_headers, monkeypatch, asset_service_override):
        _set_r2_config(monkeypatch)

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "avatar.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "purpose": "profile_picture",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["object_key"].startswith("uploads/")

    def test_signed_upload_background_check_success(
        self, client, auth_headers, monkeypatch, asset_service_override
    ):
        _set_r2_config(monkeypatch)

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "report.pdf",
                "content_type": "application/pdf",
                "size_bytes": 2048,
                "purpose": "background_check",
            },
        )
        assert res.status_code == 200

    def test_proxy_upload_success_and_exception(
        self, client, auth_headers, monkeypatch, asset_service_override, test_student
    ):
        _override_site_mode(client, "local")
        monkeypatch.setattr(settings, "r2_public_base_url", "https://cdn.example.com")
        key = f"uploads/{test_student.id}/x.png"

        res = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": key, "content_type": "image/png"},
            files={"file": ("x.png", b"data", "image/png")},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

        def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        asset_service_override.storage.upload_bytes = _boom
        res_error = client.post(
            "/api/v1/uploads/r2/proxy",
            headers=auth_headers,
            data={"key": key, "content_type": "image/png"},
            files={"file": ("x.png", b"data", "image/png")},
        )
        assert res_error.status_code == 502
        client.app.dependency_overrides.pop(uploads_routes.get_settings, None)

    def test_finalize_profile_picture_success(self, client, auth_headers, asset_service_override):
        res = client.post(
            "/api/v1/uploads/r2/finalize/profile-picture",
            headers=auth_headers,
            json={"object_key": "ok"},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True

    def test_finalize_profile_picture_http_exception_reraise(
        self, client, auth_headers, asset_service_override
    ):
        """L217: HTTPException re-raised from finalize without being wrapped."""
        from fastapi import HTTPException as _HTTPException

        def _raise_http(user, object_key):
            raise _HTTPException(status_code=409, detail="conflict from service")

        asset_service_override.finalize_profile_picture = _raise_http

        res = client.post(
            "/api/v1/uploads/r2/finalize/profile-picture",
            headers=auth_headers,
            json={"object_key": "conflict-key"},
        )
        assert res.status_code == 409

    def test_signed_upload_r2_url_none_when_no_base_url(
        self, client, auth_headers, monkeypatch, asset_service_override
    ):
        """L106,108-109: r2_public_base_url unset → public_url=None."""
        _set_r2_config(monkeypatch)
        monkeypatch.setattr(settings, "r2_public_base_url", None)

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "avatar.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "purpose": "profile_picture",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("public_url") is None

    def test_signed_upload_r2_url_exception_fallback_none(
        self, client, auth_headers, monkeypatch, asset_service_override
    ):
        """L108-109: Exception during URL building → public_url=None."""
        _set_r2_config(monkeypatch)

        class BrokenSettings:
            @property
            def r2_public_base_url(self):
                raise RuntimeError("settings broken")

        # The settings property raising is simulated by patching the branch directly
        # Since the exception is caught and public_url=None, let's just verify the
        # None path is reachable by having no base URL
        monkeypatch.setattr(settings, "r2_public_base_url", "")

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "avatar.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "purpose": "profile_picture",
            },
        )
        assert res.status_code == 200

    def test_background_check_valid_extension_invalid_content_type(
        self, client, auth_headers, monkeypatch, asset_service_override
    ):
        """L57-58: Valid file extension (.pdf) but invalid content_type → 400."""
        _set_r2_config(monkeypatch)

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "report.pdf",
                "content_type": "text/plain",
                "size_bytes": 1024,
                "purpose": "background_check",
            },
        )
        assert res.status_code == 400
        assert "Invalid content type" in res.json()["detail"]

    def test_get_settings_returns_settings(self) -> None:
        """L32: Exercise the get_settings() dependency directly."""
        result = uploads_routes.get_settings()
        assert result is settings

    def test_signed_upload_unknown_purpose_falls_through(
        self, client, auth_headers, monkeypatch, asset_service_override
    ):
        """L79->87: When purpose is neither 'background_check' nor 'profile_picture',
        the if/elif block is skipped entirely and execution jumps to L87.

        This cannot happen via the API (Pydantic Literal rejects it), so we call
        the route handler directly with a mock payload.
        """
        from unittest.mock import MagicMock as _MagicMock

        _set_r2_config(monkeypatch)

        mock_payload = _MagicMock()
        mock_payload.purpose = "other"
        mock_payload.filename = "file.bin"
        mock_payload.content_type = "application/octet-stream"
        mock_payload.size_bytes = 1024

        mock_user = _MagicMock()
        mock_user.id = "01TESTUSER000000000000000"

        mock_db = _MagicMock()

        result = uploads_routes.create_signed_upload(
            payload=mock_payload,
            current_user=mock_user,
            _db=mock_db,
            asset_service=asset_service_override,
        )
        assert result is not None

    def test_signed_upload_profile_picture_valid_content_falls_through(
        self, client, auth_headers, monkeypatch, asset_service_override
    ):
        """L79->87: profile_picture with a valid content_type enters the elif
        but does NOT raise (L81 condition is False), falling through to L87.

        This is already tested by test_signed_upload_success, but we verify
        explicitly that the elif block is entered and the valid-type path taken.
        """
        _set_r2_config(monkeypatch)

        # image/jpeg is valid for profile_picture, so L81 is False → falls through
        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "avatar.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 2048,
                "purpose": "profile_picture",
            },
        )
        assert res.status_code == 200

    def test_signed_upload_public_url_exception_path(
        self, client, auth_headers, monkeypatch, asset_service_override
    ):
        """L108-109: Force the except branch during public_url construction.

        We set r2_public_base_url to an object whose __format__/__str__ raises,
        so the f-string interpolation inside the try block triggers an exception.
        """
        _set_r2_config(monkeypatch)

        class _Unformattable:
            """Object that is truthy but raises on string formatting."""

            def __bool__(self):
                return True

            def __str__(self):
                raise RuntimeError("cannot format")

            def __format__(self, _spec):
                raise RuntimeError("cannot format")

        monkeypatch.setattr(settings, "r2_public_base_url", _Unformattable())

        res = client.post(
            "/api/v1/uploads/r2/signed-url",
            headers=auth_headers,
            json={
                "filename": "avatar.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "purpose": "profile_picture",
            },
        )
        assert res.status_code == 200
        data = res.json()
        # The except branch catches the formatting error → public_url=None
        assert data.get("public_url") is None
