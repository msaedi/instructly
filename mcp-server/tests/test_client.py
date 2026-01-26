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
