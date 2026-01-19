import io
from types import SimpleNamespace

from PIL import Image
import pytest

from app.models.user import User
from app.services.personal_asset_service import PersonalAssetService
from app.services.r2_storage_client import PresignedUrl


def _png_bytes() -> bytes:
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_finalize_profile_picture_updates_user(db):
    # Create user
    user = User(
        email="asset_user@example.com",
        first_name="Asset",
        last_name="User",
        phone="+12125551234",
        zip_code="10001",
        hashed_password="x",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Build service with injected stubbed storage to avoid requiring R2 config
    class _StubStorage:
        def download_bytes(self, key):
            return _png_bytes()

        def upload_bytes(self, key, content, ct):
            uploaded.append(key)
            return True, 200

        def delete_object(self, key):
            return True

    uploaded = []
    svc = PersonalAssetService(db, storage=_StubStorage())

    ok = svc.finalize_profile_picture(user, "uploads/profile_picture/mock/obj.png")
    assert ok is True

    db.refresh(user)
    assert user.profile_picture_version > 0
    assert user.profile_picture_key is not None
    assert len(uploaded) == 3


def test_build_storage_falls_back_when_disabled(monkeypatch):
    from app.services import personal_asset_service as module

    monkeypatch.setattr(module, "_FALLBACK_STORAGE_WARNED", False)
    monkeypatch.setattr(module.settings, "r2_enabled", False, raising=False)

    service = PersonalAssetService(db=None)
    assert isinstance(service.storage, module.NullStorageClient)


def test_generate_presigned_with_limits_backpressure(monkeypatch):
    from app.services import personal_asset_service as module

    class DummySemaphore:
        def acquire(self, timeout=None):
            return False

        def release(self):
            return None

    class DummyStorage:
        def generate_presigned_get(self, object_key, expires_seconds, extra_query_params):
            return PresignedUrl(url="u", headers={}, expires_at="t")

    monkeypatch.setattr(module, "_STORAGE_SEMAPHORE", DummySemaphore())
    service = PersonalAssetService(db=None, storage=DummyStorage())

    assert service._generate_presigned_with_limits("obj", 1, "display") is None


def test_generate_presigned_with_limits_timeout(monkeypatch):
    from app.services import personal_asset_service as module

    class DummyFuture:
        def result(self, timeout=None):
            raise module.FuturesTimeoutError()

    class DummyExecutor:
        def submit(self, fn):
            return DummyFuture()

    class DummySemaphore:
        def acquire(self, timeout=None):
            return True

        def release(self):
            return None

    class DummyStorage:
        def generate_presigned_get(self, object_key, expires_seconds, extra_query_params):
            return PresignedUrl(url="u", headers={}, expires_at="t")

    monkeypatch.setattr(module, "_STORAGE_EXECUTOR", DummyExecutor())
    monkeypatch.setattr(module, "_STORAGE_SEMAPHORE", DummySemaphore())
    service = PersonalAssetService(db=None, storage=DummyStorage())

    assert service._generate_presigned_with_limits("obj", 1, "display") is None


def test_generate_presigned_with_limits_error(monkeypatch):
    from app.services import personal_asset_service as module

    class DummyFuture:
        def result(self, timeout=None):
            raise RuntimeError("boom")

    class DummyExecutor:
        def submit(self, fn):
            return DummyFuture()

    class DummySemaphore:
        def acquire(self, timeout=None):
            return True

        def release(self):
            return None

    class DummyStorage:
        def generate_presigned_get(self, object_key, expires_seconds, extra_query_params):
            return PresignedUrl(url="u", headers={}, expires_at="t")

    monkeypatch.setattr(module, "_STORAGE_EXECUTOR", DummyExecutor())
    monkeypatch.setattr(module, "_STORAGE_SEMAPHORE", DummySemaphore())
    service = PersonalAssetService(db=None, storage=DummyStorage())

    assert service._generate_presigned_with_limits("obj", 1, "display") is None


def test_get_presigned_view_cache_hit(monkeypatch):
    from app.services import personal_asset_service as module

    class DummyCache:
        def __init__(self, value):
            self.value = value

        def get(self, key):
            return self.value

    class DummyStorage:
        def generate_presigned_get(self, object_key, expires_seconds, extra_query_params):
            raise AssertionError("should not be called")

    monkeypatch.setattr(module, "_STORAGE_SEMAPHORE", module.threading.Semaphore(1))

    cache = DummyCache({"url": "cached", "expires_at": "later"})
    service = PersonalAssetService(db=None, storage=DummyStorage(), cache_service=cache)
    view = service._get_presigned_view_for_user("user1", 2, "display")
    assert view.url == "cached"


def test_get_presigned_view_cache_set_error(monkeypatch):
    from app.services import personal_asset_service as module

    class DummyFuture:
        def __init__(self, value):
            self.value = value

        def result(self, timeout=None):
            return self.value

    class DummyExecutor:
        def submit(self, fn):
            return DummyFuture(fn())

    class DummySemaphore:
        def acquire(self, timeout=None):
            return True

        def release(self):
            return None

    class DummyCache:
        def get(self, key):
            return None

        def set(self, *args, **kwargs):
            raise RuntimeError("cache down")

    class DummyStorage:
        def generate_presigned_get(self, object_key, expires_seconds, extra_query_params):
            return PresignedUrl(url="fresh", headers={}, expires_at="later")

    monkeypatch.setattr(module, "_STORAGE_EXECUTOR", DummyExecutor())
    monkeypatch.setattr(module, "_STORAGE_SEMAPHORE", DummySemaphore())

    service = PersonalAssetService(
        db=None,
        storage=DummyStorage(),
        cache_service=DummyCache(),
    )
    view = service._get_presigned_view_for_user("user1", 1, "thumb")
    assert view.url == "fresh"


def test_finalize_profile_picture_placeholder_upload_warnings(monkeypatch):
    class DummyImages:
        def process_profile_picture(self, data, content_type):
            return SimpleNamespace(
                original=b"orig",
                display_400=b"disp",
                thumb_200=b"thumb",
            )

    class DummyStorage:
        def __init__(self):
            self.calls = 0

        def download_bytes(self, key):
            return None

        def upload_bytes(self, key, content, ct):
            self.calls += 1
            if self.calls == 1:
                return False, 500
            if self.calls == 2:
                raise RuntimeError("upload failed")
            return True, 200

        def delete_object(self, key):
            raise RuntimeError("delete failed")

    class DummyUsers:
        def update_profile(self, **kwargs):
            return True

    class DummyCache:
        def delete_pattern(self, pattern):
            raise RuntimeError("cache down")

    user = SimpleNamespace(id="user1", profile_picture_version=0)
    service = PersonalAssetService(
        db=None,
        storage=DummyStorage(),
        images=DummyImages(),
        users_repo=DummyUsers(),
        cache_service=DummyCache(),
    )

    assert service.finalize_profile_picture(user, "uploads/profile_picture/x.png") is True


def test_finalize_profile_picture_update_failure():
    class DummyImages:
        def process_profile_picture(self, data, content_type):
            return SimpleNamespace(
                original=b"orig",
                display_400=b"disp",
                thumb_200=b"thumb",
            )

    class DummyStorage:
        def download_bytes(self, key):
            return b"data"

        def upload_bytes(self, key, content, ct):
            return True, 200

        def delete_object(self, key):
            return True

    class DummyUsers:
        def update_profile(self, **kwargs):
            return None

    user = SimpleNamespace(id="user2", profile_picture_version=0)
    service = PersonalAssetService(
        db=None,
        storage=DummyStorage(),
        images=DummyImages(),
        users_repo=DummyUsers(),
        cache_service=None,
    )

    with pytest.raises(RuntimeError, match="Failed to update user record"):
        service.finalize_profile_picture(user, "uploads/profile_picture/x.png")


def test_delete_profile_picture_handles_no_version():
    class DummyStorage:
        def delete_object(self, key):
            raise AssertionError("should not be called")

    service = PersonalAssetService(db=None, storage=DummyStorage())
    user = SimpleNamespace(id="user3", profile_picture_version=0)
    assert service.delete_profile_picture(user) is True


def test_delete_profile_picture_cleans_and_invalidates():
    class DummyStorage:
        def delete_object(self, key):
            raise RuntimeError("delete failed")

    class DummyUsers:
        def update_profile(self, **kwargs):
            return True

    class DummyCache:
        def delete_pattern(self, pattern):
            raise RuntimeError("cache down")

    service = PersonalAssetService(
        db=None,
        storage=DummyStorage(),
        users_repo=DummyUsers(),
        cache_service=DummyCache(),
    )
    user = SimpleNamespace(id="user4", profile_picture_version=1)
    assert service.delete_profile_picture(user) is True


def test_get_profile_picture_view_errors(monkeypatch):
    from app.services import personal_asset_service as module

    class DummyUsers:
        def get_by_id(self, *args, **kwargs):
            return None

    service = PersonalAssetService(db=None, users_repo=DummyUsers())

    monkeypatch.setattr(module, "with_db_retry", lambda name, fn: fn())
    with pytest.raises(ValueError, match="No profile picture"):
        service.get_profile_picture_view("user5")


def test_get_profile_picture_view_missing_presigned(monkeypatch):
    from app.services import personal_asset_service as module

    class DummyUsers:
        def get_by_id(self, *args, **kwargs):
            return SimpleNamespace(id="user6", profile_picture_version=2)

    service = PersonalAssetService(db=None, users_repo=DummyUsers())

    monkeypatch.setattr(module, "with_db_retry", lambda name, fn: fn())
    monkeypatch.setattr(service, "_get_presigned_view_for_user", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="No profile picture"):
        service.get_profile_picture_view("user6")


def test_get_profile_picture_urls_batch_normalizes(monkeypatch):
    from app.services import personal_asset_service as module

    class DummyUsers:
        def get_profile_picture_versions(self, user_ids):
            return {"user7": 2}

    service = PersonalAssetService(db=None, users_repo=DummyUsers())

    monkeypatch.setattr(module, "with_db_retry", lambda name, fn: fn())
    monkeypatch.setattr(
        service,
        "_get_presigned_view_for_user",
        lambda user_id, version, variant: SimpleNamespace(url="u", expires_at="t"),
    )

    result = service.get_profile_picture_urls(["user7", " ", "user7", "user8"])
    assert "user7" in result
    assert result["user7"] is not None
    assert result["user8"] is None
