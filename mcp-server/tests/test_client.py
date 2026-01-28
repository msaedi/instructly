from unittest.mock import patch

import httpx
import pytest
import respx
from instainstru_mcp.auth import MCPAuth
from instainstru_mcp.client import (
    BackendAuthError,
    BackendConnectionError,
    BackendNotFoundError,
    InstaInstruClient,
)
from instainstru_mcp.config import Settings


@pytest.mark.asyncio
@respx.mock
async def test_client_success():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, json={"data": {"ok": True}}
    )

    result = await client.get_funnel_summary()
    assert result["data"]["ok"] is True
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_auth_error():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(401)

    with pytest.raises(BackendAuthError):
        await client.get_funnel_summary()
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_not_found():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(404)

    with pytest.raises(BackendNotFoundError):
        await client.get_funnel_summary()
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_network_error():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").mock(
        side_effect=httpx.ConnectError("boom")
    )

    with pytest.raises(BackendConnectionError):
        await client.get_funnel_summary()
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_uses_m2m_token_and_caches():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="secret",
        workos_m2m_token_url="https://workos.test/oauth/token",
        workos_m2m_audience="https://api.instainstru.test",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    token_route = respx.post("https://workos.test/oauth/token").respond(
        200, json={"access_token": "m2m-token", "expires_in": 3600}
    )
    api_route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, json={"data": {"ok": True}}
    )

    await client.get_funnel_summary()
    await client.get_funnel_summary()

    assert token_route.call_count == 1
    assert api_route.call_count == 2
    assert api_route.calls[0].request.headers.get("Authorization") == "Bearer m2m-token"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_falls_back_to_static_token_on_m2m_failure():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="secret",
        workos_m2m_token_url="https://workos.test/oauth/token",
        workos_m2m_audience="https://api.instainstru.test",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.post("https://workos.test/oauth/token").respond(500)
    api_route = respx.get("https://api.instainstru.test/api/v1/admin/mcp/founding/funnel").respond(
        200, json={"data": {"ok": True}}
    )

    result = await client.get_funnel_summary()
    assert result["data"]["ok"] is True
    assert api_route.calls[0].request.headers.get("Authorization") == "Bearer svc"

    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_client_m2m_failure_without_static_token_raises():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="",
        workos_m2m_client_id="client_123",
        workos_m2m_client_secret="secret",
        workos_m2m_token_url="https://workos.test/oauth/token",
        workos_m2m_audience="https://api.instainstru.test",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    respx.post("https://workos.test/oauth/token").respond(500)

    with pytest.raises(BackendConnectionError):
        await client.get_funnel_summary()

    await client.aclose()


@pytest.mark.asyncio
async def test_instructor_detail_url_encodes_name_with_spaces():
    settings = Settings(
        api_base_url="https://api.instainstru.test",
        api_service_token="svc",
    )
    auth = MCPAuth(settings)
    client = InstaInstruClient(settings, auth)

    with patch.object(client, "call") as mock_call:
        mock_call.return_value = {"data": {}}
        await client.get_instructor_detail("Jane Doe")
        mock_call.assert_called_once_with(
            "GET",
            "/api/v1/admin/mcp/instructors/Jane%20Doe",
        )

    await client.aclose()
