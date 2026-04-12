from app.utils import profile_picture_urls as module


class _StubPresignedGet:
    def __init__(self, url: str):
        self.url = url
        self.headers = {}
        self.expires_at = "2026-01-01T00:00:00Z"


class _StubR2StorageClient:
    def generate_presigned_get(self, object_key, expires_seconds=3600, extra_query_params=None):
        version = (extra_query_params or {}).get("v", "0")
        return _StubPresignedGet(f"https://signed.example.com/{object_key}?v={version}")


def test_build_photo_url_returns_thumb_presigned_url(monkeypatch):
    monkeypatch.setattr(module, "R2StorageClient", _StubR2StorageClient)

    result = module.build_photo_url(
        "private/personal-assets/profile-pictures/usr_123/v7/original.jpg",
        variant="thumb",
    )

    assert (
        result
        == "https://signed.example.com/private/personal-assets/profile-pictures/usr_123/v7/thumb_200x200.jpg?v=7"
    )


def test_build_photo_url_uses_24_hour_ttl(monkeypatch):
    captured: dict[str, int | None] = {"expires_seconds": None}

    class _CapturingR2StorageClient:
        def generate_presigned_get(self, object_key, expires_seconds=3600, extra_query_params=None):
            captured["expires_seconds"] = expires_seconds
            return _StubPresignedGet(f"https://signed.example.com/{object_key}")

    monkeypatch.setattr(module, "R2StorageClient", _CapturingR2StorageClient)

    result = module.build_photo_url(
        "private/personal-assets/profile-pictures/usr_123/v7/original.jpg",
        variant="thumb",
    )

    assert result == "https://signed.example.com/private/personal-assets/profile-pictures/usr_123/v7/thumb_200x200.jpg"
    assert captured["expires_seconds"] == 86400


def test_build_photo_url_returns_none_when_key_missing():
    assert module.build_photo_url(None, variant="thumb") is None


def test_build_photo_url_returns_none_when_presign_fails(monkeypatch):
    class _BrokenR2StorageClient:
        def __init__(self):
            raise RuntimeError("bad config")

    monkeypatch.setattr(module, "R2StorageClient", _BrokenR2StorageClient)

    assert (
        module.build_photo_url(
            "private/personal-assets/profile-pictures/usr_123/v7/original.jpg",
            variant="thumb",
        )
        is None
    )
