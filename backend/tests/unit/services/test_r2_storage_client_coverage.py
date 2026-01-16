from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import r2_storage_client


class _FakeSecret:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


@pytest.fixture
def r2_settings(monkeypatch) -> SimpleNamespace:
    fake_settings = SimpleNamespace(
        r2_bucket_name="bucket",
        r2_access_key_id="ACCESS",
        r2_secret_access_key=_FakeSecret("SECRET"),
        r2_account_id="acct123",
    )
    monkeypatch.setattr(r2_storage_client, "settings", fake_settings)
    return fake_settings


def test_init_missing_config(monkeypatch) -> None:
    monkeypatch.setattr(
        r2_storage_client,
        "settings",
        SimpleNamespace(
            r2_bucket_name="",
            r2_access_key_id=None,
            r2_secret_access_key=None,
            r2_account_id="acct",
        ),
    )

    with pytest.raises(RuntimeError, match="R2 configuration is missing"):
        r2_storage_client.R2StorageClient()


def test_generate_presigned_put_and_get(r2_settings) -> None:
    client = r2_storage_client.R2StorageClient()
    put_url = client.generate_presigned_put("path/file.txt", "text/plain", expires_seconds=123)
    get_url = client.generate_presigned_get(
        "path/file.txt", extra_query_params={"response-content-disposition": "inline"}
    )

    assert f"/{r2_settings.r2_bucket_name}/path/file.txt" in put_url.url
    assert "X-Amz-Signature=" in put_url.url
    assert put_url.headers["Content-Type"] == "text/plain"
    assert "response-content-disposition=inline" in get_url.url


def test_upload_bytes_success(r2_settings, monkeypatch) -> None:
    client = r2_storage_client.R2StorageClient()

    class _Resp:
        status_code = 201

    monkeypatch.setattr(r2_storage_client.requests, "put", lambda *_args, **_kwargs: _Resp())
    ok, status = client.upload_bytes("obj", b"data", "application/octet-stream")

    assert ok is True
    assert status == 201


def test_upload_bytes_failure_returns_none(r2_settings, monkeypatch) -> None:
    client = r2_storage_client.R2StorageClient()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(r2_storage_client.requests, "put", _boom)
    ok, status = client.upload_bytes("obj", b"data", "application/octet-stream")

    assert ok is False
    assert status is None


def test_download_bytes_success_and_missing(r2_settings, monkeypatch) -> None:
    client = r2_storage_client.R2StorageClient()

    class _Resp:
        def __init__(self, status_code: int, content: bytes = b"") -> None:
            self.status_code = status_code
            self.content = content

    monkeypatch.setattr(r2_storage_client.requests, "get", lambda *_args, **_kwargs: _Resp(200, b"ok"))
    assert client.download_bytes("obj") == b"ok"

    monkeypatch.setattr(r2_storage_client.requests, "get", lambda *_args, **_kwargs: _Resp(404))
    assert client.download_bytes("obj") is None


def test_download_bytes_exception(r2_settings, monkeypatch) -> None:
    client = r2_storage_client.R2StorageClient()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(r2_storage_client.requests, "get", _boom)
    assert client.download_bytes("obj") is None


def test_delete_object_paths(r2_settings, monkeypatch) -> None:
    client = r2_storage_client.R2StorageClient()

    class _Resp:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    monkeypatch.setattr(
        r2_storage_client.requests, "delete", lambda *_args, **_kwargs: _Resp(204)
    )
    assert client.delete_object("obj") is True

    monkeypatch.setattr(
        r2_storage_client.requests, "delete", lambda *_args, **_kwargs: _Resp(404)
    )
    assert client.delete_object("obj") is True

    monkeypatch.setattr(
        r2_storage_client.requests, "delete", lambda *_args, **_kwargs: _Resp(500)
    )
    assert client.delete_object("obj") is False


def test_delete_object_exception(r2_settings, monkeypatch) -> None:
    client = r2_storage_client.R2StorageClient()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(r2_storage_client.requests, "delete", _boom)
    assert client.delete_object("obj") is False
