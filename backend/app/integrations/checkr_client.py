"""Minimal Checkr API client for instructor background checks."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class CheckrError(RuntimeError):
    """Raised when the Checkr API responds with an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CheckrClient:
    """Thin async client for the Checkr REST API."""

    def __init__(
        self,
        *,
        api_key: str | SecretStr,
        base_url: str = "https://api.checkr.com/v1",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        secret_value = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not secret_value:
            raise ValueError("Checkr API key must be provided")

        self._api_key = secret_value
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def create_candidate(self, **payload: Any) -> dict[str, Any]:
        """Create a new candidate in Checkr."""

        body = {key: value for key, value in payload.items() if value is not None}
        return await self._post("/candidates", json_body=body)

    async def create_invitation(self, *, candidate_id: str, package: str) -> dict[str, Any]:
        """Create a hosted invitation for a candidate."""

        json_body = {"candidate_id": candidate_id, "package": package}
        return await self._post("/invitations", json_body=json_body)

    async def _post(self, path: str, *, json_body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"

        async with httpx.AsyncClient(
            timeout=self._timeout,
            auth=(self._api_key, ""),
            transport=self._transport,
        ) as client:
            try:
                response = await client.post(url, json=json_body)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                snippet = exc.response.text[:500]
                logger.error("Checkr API error %s for %s: %s", status, path, snippet)
                raise CheckrError(
                    message=f"Checkr API responded with status {status}",
                    status_code=status,
                ) from exc
            except httpx.RequestError as exc:
                logger.error("Checkr request failure for %s: %s", path, str(exc))
                raise CheckrError("Failed to reach Checkr API") from exc

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON from Checkr for %s: %s", path, response.text)
            raise CheckrError("Received malformed JSON from Checkr") from exc
