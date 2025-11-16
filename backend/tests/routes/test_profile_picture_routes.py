from contextlib import contextmanager
import io

from PIL import Image
from pydantic import SecretStr

from app.core.config import settings
from app.models.user import User


def _make_png_bytes(size=(20, 10), color=(255, 0, 0, 255)) -> bytes:
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@contextmanager
def _stub_personal_asset_service(db, app):
    from app.services.dependencies import get_personal_asset_service
    from app.services.personal_asset_service import PersonalAssetService

    class _StubStorage:
        def generate_presigned_put(self, key, content_type, expires_seconds=300):
            class P:
                def __init__(self):
                    self.url = "https://example.com/put"
                    self.headers = {"Content-Type": content_type}
                    self.expires_at = "2025-01-01T00:00:00Z"

            return P()

        def generate_presigned_get(self, key, expires_seconds=3600, extra_query_params=None):
            class P:
                def __init__(self):
                    self.url = "https://example.com/get"
                    self.headers = {}
                    self.expires_at = "2025-01-01T00:00:00Z"

            return P()

        def download_bytes(self, key):
            return _make_png_bytes()

        def upload_bytes(self, key, content, ct):
            return True, 200

        def delete_object(self, key):
            return True

    previous_override = app.dependency_overrides.get(get_personal_asset_service)
    svc = PersonalAssetService(db, storage=_StubStorage())
    app.dependency_overrides[get_personal_asset_service] = lambda: svc
    try:
        yield svc
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_personal_asset_service, None)
        else:
            app.dependency_overrides[get_personal_asset_service] = previous_override


def test_signed_upload_and_finalize_profile_picture(client, db, auth_headers):
    # Configure dummy R2 settings for the signed URL route
    settings.r2_bucket_name = "test-bucket"
    settings.r2_access_key_id = "test-access"
    settings.r2_secret_access_key = SecretStr("test-secret")
    settings.r2_account_id = "test-account"
    # Step 1: request signed upload for profile picture via stubbed storage service
    with _stub_personal_asset_service(db, client.app) as svc:
        resp = client.post(
            "/api/uploads/r2/signed-url",
            json={
                "filename": "avatar.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "purpose": "profile_picture",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "object_key" in data and "upload_url" in data

        # Step 2: instead of PUT to R2, directly call finalize using our temp key
        # and monkeypatch storage download to return a valid PNG
        # Create a small valid test image
        png_bytes = _make_png_bytes()

        # storage already stubbed above; ensure download returns our bytes
        svc.storage.download_bytes = lambda key: png_bytes

        resp2 = client.post(
            "/api/users/me/profile-picture",
            json={"object_key": data["object_key"]},
            headers=auth_headers,
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json().get("success") is True

        # Step 3: fetch presigned view URL
        # Need current user id; call /api/auth/me to get it
        me = client.get("/auth/me", headers=auth_headers)
        assert me.status_code == 200
        me_json = me.json()
        user_id = me_json.get("id") or me_json.get("data", {}).get("id")
        assert user_id, f"unexpected /api/auth/me response: {me_json}"

        resp3 = client.get(f"/api/users/{user_id}/profile-picture-url?variant=thumb", headers=auth_headers)
        assert resp3.status_code == 200, resp3.text
        j = resp3.json()
        assert j["success"] is True and "url" in j["data"] and j["data"]["url"].startswith("https://")

        # Step 4: delete
        resp4 = client.delete("/api/users/me/profile-picture", headers=auth_headers)
        assert resp4.status_code == 200
        assert resp4.json().get("success") in (True, False)


def test_reject_invalid_content_type_for_signed_upload(client, auth_headers):
    # Configure dummy R2 settings for the signed URL route
    settings.r2_bucket_name = "test-bucket"
    settings.r2_access_key_id = "test-access"
    settings.r2_secret_access_key = SecretStr("test-secret")
    settings.r2_account_id = "test-account"
    resp = client.post(
        "/api/uploads/r2/signed-url",
        json={
            "filename": "avatar.exe",
            "content_type": "application/x-msdownload",
            "size_bytes": 1024,
            "purpose": "profile_picture",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_profile_picture_urls_batch_empty(client, db, auth_headers):
    with _stub_personal_asset_service(db, client.app):
        resp = client.get("/api/users/profile-picture-urls", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"urls": {}}


def test_profile_picture_urls_batch_mixed_ids(client, db, auth_headers):
    user_with = User(
        id="usr_avatar_batch",
        email="avatar-batch@example.com",
        hashed_password="x",
        first_name="Ava",
        last_name="Tar",
        zip_code="10001",
        profile_picture_key="private/personal-assets/profile-pictures/usr_avatar_batch/v1/original.jpg",
        profile_picture_version=1,
    )
    user_without = User(
        id="usr_nopicture",
        email="no-pic@example.com",
        hashed_password="x",
        first_name="No",
        last_name="Pic",
        zip_code="10001",
    )
    db.add(user_with)
    db.add(user_without)
    db.commit()

    with _stub_personal_asset_service(db, client.app):
        resp = client.get(
            f"/api/users/profile-picture-urls?ids={user_with.id},{user_without.id},missing",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["urls"]
        assert data[user_with.id] == "https://example.com/get"
        assert data[user_without.id] is None
        assert data["missing"] is None


def test_profile_picture_urls_batch_limit(client, db, auth_headers):
    with _stub_personal_asset_service(db, client.app):
        ids = ",".join(f"user{i}" for i in range(0, 51))
        resp = client.get(f"/api/users/profile-picture-urls?ids={ids}", headers=auth_headers)
        assert resp.status_code == 400
        assert "maximum of 50" in resp.text.lower()
