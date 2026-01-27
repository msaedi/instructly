"""WorkOS OAuth helper client."""

from __future__ import annotations

from urllib.parse import urlencode

import httpx


class WorkOSClient:
    def __init__(self, domain: str, client_id: str, client_secret: str) -> None:
        self.domain = domain
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Build WorkOS authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": "openid profile email",
        }
        return f"{self.base_url}/oauth2/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for tokens."""
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
        response.raise_for_status()
        return response.json()

    async def get_userinfo(self, access_token: str) -> dict:
        """Get user info from WorkOS."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/oauth2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
        response.raise_for_status()
        return response.json()

    async def get_jwks(self) -> dict:
        """Fetch WorkOS JWKS for token validation."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/oauth2/jwks",
                timeout=10.0,
            )
        response.raise_for_status()
        return response.json()
