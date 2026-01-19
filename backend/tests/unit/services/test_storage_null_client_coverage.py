from __future__ import annotations

from app.services.storage_null_client import NullStorageClient


def test_null_storage_presigned_urls() -> None:
    client = NullStorageClient()

    put_url = client.generate_presigned_put("key", "text/plain")
    get_url = client.generate_presigned_get("key")
    delete_url = client.generate_presigned_delete("key")

    assert put_url.url == ""
    assert get_url.url == ""
    assert delete_url.url == ""
    assert put_url.headers == {}
    assert put_url.expires_at


def test_null_storage_actions() -> None:
    client = NullStorageClient()

    ok, size = client.upload_bytes("key", b"data", "text/plain")
    assert ok is True
    assert size is None

    assert client.download_bytes("key") is None
    assert client.delete_object("key") is True
    assert client.list_objects(prefix="prefix") == []
