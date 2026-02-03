from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx
from fastmcp import FastMCP
from instainstru_mcp.tools import deploy


def _mock_scope(monkeypatch):
    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(deploy, "get_http_request", fake_request)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.asyncio
@respx.mock
async def test_check_service_extracts_version_info():
    async with httpx.AsyncClient() as http:
        respx.get("https://api.instainstru.com/api/v1/health").respond(
            200,
            json={
                "status": "healthy",
                "git_sha": "abc1234",
                "version": "1.0.0",
                "uptime": 123,
                "commit": "def5678",
            },
        )
        result = await deploy._check_service(
            http, "api", "https://api.instainstru.com", "/api/v1/health"
        )

    assert result["status"] == "up"
    assert result["git_sha"] == "def5678"
    assert result["version"] == "1.0.0"
    assert result["uptime_seconds"] == 123
    assert result["http_status"] == 200
    assert "response_time_ms" in result


@pytest.mark.asyncio
@respx.mock
async def test_check_service_extracts_uptime_seconds():
    async with httpx.AsyncClient() as http:
        respx.get("https://api.instainstru.com/api/v1/health").respond(
            200,
            json={
                "status": "healthy",
                "git_sha": "abc1234",
                "uptime_seconds": 321,
            },
        )
        result = await deploy._check_service(
            http, "api", "https://api.instainstru.com", "/api/v1/health"
        )

    assert result["uptime_seconds"] == 321


@pytest.mark.asyncio
@respx.mock
async def test_check_service_non_json_response():
    async with httpx.AsyncClient() as http:
        respx.get("https://api.instainstru.com/api/v1/health").respond(
            200,
            content=b"ok",
            headers={"X-Commit-Sha": "abc123"},
        )
        result = await deploy._check_service(
            http, "api", "https://api.instainstru.com", "/api/v1/health"
        )

    assert result["status"] == "up"
    assert result["git_sha"] == "abc123"


@pytest.mark.asyncio
@respx.mock
async def test_check_service_auth_required_status():
    async with httpx.AsyncClient() as http:
        respx.get("https://api.instainstru.com/api/v1/health").respond(401, json={"detail": "auth"})
        result = await deploy._check_service(
            http, "api", "https://api.instainstru.com", "/api/v1/health"
        )

    assert result["status"] == "up"
    assert result["note"] == "auth_required"
    assert result["http_status"] == 401


@pytest.mark.asyncio
@respx.mock
async def test_check_service_missing_health_endpoint():
    async with httpx.AsyncClient() as http:
        respx.get("https://api.instainstru.com/api/v1/health").respond(404)
        result = await deploy._check_service(
            http, "api", "https://api.instainstru.com", "/api/v1/health"
        )

    assert result["status"] == "unknown"
    assert result["note"] == "health_endpoint_not_found"


@pytest.mark.asyncio
async def test_check_service_timeout_handling(monkeypatch):
    async with httpx.AsyncClient() as http:

        async def raise_timeout(*_args, **_kwargs):
            raise httpx.TimeoutException("timeout")

        monkeypatch.setattr(http, "get", raise_timeout)
        result = await deploy._check_service(
            http, "api", "https://api.instainstru.com", "/api/v1/health"
        )

    assert result["status"] == "down"
    assert result["error"] == "timeout"


@pytest.mark.asyncio
async def test_check_service_generic_error(monkeypatch):
    async with httpx.AsyncClient() as http:

        async def raise_error(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(http, "get", raise_error)
        result = await deploy._check_service(
            http, "api", "https://api.instainstru.com", "/api/v1/health"
        )

    assert result["status"] == "down"
    assert "boom" in result["error"]


@pytest.mark.asyncio
async def test_check_environment_exception_path(monkeypatch):
    async def raise_exception(*_args, **_kwargs):
        raise RuntimeError("bad")

    monkeypatch.setattr(deploy, "_check_service", raise_exception)

    async with httpx.AsyncClient() as http:
        result = await deploy._check_environment(
            http,
            "production",
            {"api": "https://api.instainstru.com"},
        )

    assert result["status"] == "down"
    assert result["services"]["api"]["status"] == "down"


@pytest.mark.asyncio
async def test_check_environment_all_unknown(monkeypatch):
    async def fake_check_service(_http, _name, _url, _path):
        return {"status": "unknown", "url": _url}

    monkeypatch.setattr(deploy, "_check_service", fake_check_service)

    async with httpx.AsyncClient() as http:
        result = await deploy._check_environment(
            http,
            "production",
            {"api": "https://api.instainstru.com", "mcp": "https://mcp.instainstru.com"},
        )

    assert result["status"] == "unknown"


def test_version_drift_detection_no_drift():
    envs = {
        "production": {
            "services": {
                "api": {"git_sha": "abc123"},
                "mcp": {"git_sha": "abc123"},
            }
        }
    }
    result = deploy._detect_version_drift(envs)
    assert result["detected"] is False
    assert result["details"] is None


def test_version_drift_detection_with_drift():
    envs = {
        "production": {
            "services": {
                "api": {"git_sha": "abc123"},
                "mcp": {"git_sha": "def456"},
            }
        }
    }
    result = deploy._detect_version_drift(envs)
    assert result["detected"] is True
    assert result["details"]["production/api"] == "abc123"


@pytest.mark.asyncio
@respx.mock
async def test_deploy_overview_all_healthy(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = deploy.register_tools(mcp)

    respx.get("https://api.instainstru.com/api/v1/health").respond(200, json={"git_sha": "abc123"})
    respx.get("https://mcp.instainstru.com/health").respond(200, json={"git_sha": "abc123"})
    respx.get("https://instainstru.com/api/health").respond(200, json={})

    result = await tools["instainstru_deploy_overview"](env="production")

    assert result["summary"]["all_services_up"] is True
    assert result["environments"]["production"]["status"] == "ok"
    assert result["summary"]["services_checked"] == 3
    assert result["version_drift"] is False


@pytest.mark.asyncio
async def test_deploy_overview_all_down_avg_response_time_none(monkeypatch):
    _mock_scope(monkeypatch)

    async def fake_check_environment(_http, _env, _services):
        return {
            "status": "down",
            "services": {
                "api": {"status": "down", "url": "x", "checked_at": _now_iso()},
                "mcp": {"status": "down", "url": "y", "checked_at": _now_iso()},
            },
        }

    monkeypatch.setattr(deploy, "_check_environment", fake_check_environment)
    mcp = FastMCP("test")
    tools = deploy.register_tools(mcp)

    result = await tools["instainstru_deploy_overview"](env="preview")

    assert result["summary"]["services_down"] == 2
    assert result["summary"]["avg_response_time_ms"] is None


@pytest.mark.asyncio
@respx.mock
async def test_deploy_overview_partial_failure(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = deploy.register_tools(mcp)

    respx.get("https://api.instainstru.com/api/v1/health").respond(500, json={})
    respx.get("https://mcp.instainstru.com/health").respond(200, json={})
    respx.get("https://instainstru.com/api/health").respond(200, json={})

    result = await tools["instainstru_deploy_overview"](env="production")

    assert result["environments"]["production"]["status"] == "degraded"
    assert result["summary"]["services_up"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_deploy_overview_include_preview(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = deploy.register_tools(mcp)

    respx.get("https://api.instainstru.com/api/v1/health").respond(200, json={})
    respx.get("https://mcp.instainstru.com/health").respond(200, json={})
    respx.get("https://instainstru.com/api/health").respond(200, json={})
    respx.get("https://preview-api.instainstru.com/api/v1/health").respond(200, json={})
    respx.get("https://preview-mcp.instainstru.com/health").respond(200, json={})
    respx.get("https://preview.instainstru.com/api/health").respond(200, json={})

    result = await tools["instainstru_deploy_overview"](env="production", include_preview=True)

    assert set(result["meta"]["environments_checked"]) == {"production", "preview"}
    assert result["summary"]["services_checked"] == 6


@pytest.mark.asyncio
async def test_deploy_overview_invalid_env(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = deploy.register_tools(mcp)

    with pytest.raises(ValueError):
        await tools["instainstru_deploy_overview"](env="staging")


@pytest.mark.asyncio
@respx.mock
async def test_deploy_overview_all_down(monkeypatch):
    _mock_scope(monkeypatch)
    mcp = FastMCP("test")
    tools = deploy.register_tools(mcp)

    respx.get("https://api.instainstru.com/api/v1/health").respond(503, json={})
    respx.get("https://mcp.instainstru.com/health").respond(503, json={})
    respx.get("https://instainstru.com/api/health").respond(503, json={})

    result = await tools["instainstru_deploy_overview"](env="production")

    assert result["environments"]["production"]["status"] == "degraded"
    assert result["summary"]["services_up"] == 0


def test_require_scope_variants(monkeypatch):
    def fake_request_jwt():
        class Dummy:
            scope = {"auth": {"method": "jwt", "claims": {}}}

        return Dummy()

    monkeypatch.setattr(deploy, "get_http_request", fake_request_jwt)
    deploy._require_scope("mcp:read")

    def fake_request_none():
        class Dummy:
            scope = {"auth": {"method": "oauth", "claims": {}}}

        return Dummy()

    monkeypatch.setattr(deploy, "get_http_request", fake_request_none)
    with pytest.raises(PermissionError):
        deploy._require_scope("mcp:write")
