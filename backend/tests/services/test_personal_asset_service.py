import io

from PIL import Image

from app.models.user import User
from app.services.personal_asset_service import PersonalAssetService


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
