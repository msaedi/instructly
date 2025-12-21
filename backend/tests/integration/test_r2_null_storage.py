from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.main import fastapi_app as app
from app.services.dependencies import get_personal_asset_service
from app.services.personal_asset_service import PersonalAssetService
from app.services.storage_null_client import NullStorageClient


def test_personal_asset_service_falls_back_to_null_storage(monkeypatch, db):
    monkeypatch.setattr(settings, "r2_enabled", False, raising=False)
    monkeypatch.setattr(settings, "r2_bucket_name", "", raising=False)
    monkeypatch.setattr(settings, "r2_access_key_id", "", raising=False)
    monkeypatch.setattr(settings, "r2_account_id", "", raising=False)
    monkeypatch.setattr(settings, "r2_secret_access_key", SecretStr(""), raising=False)

    svc = PersonalAssetService(db)
    assert isinstance(svc.storage, NullStorageClient)

    injected = get_personal_asset_service(db)
    assert isinstance(injected.storage, NullStorageClient)

    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
