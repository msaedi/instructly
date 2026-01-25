"""HTTP client for the InstaInstru backend MCP endpoints."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from .auth import MCPAuth
from .config import Settings


class BackendError(Exception):
    """Base error for backend request failures."""


class BackendAuthError(BackendError):
    """Raised when backend rejects authentication."""


class BackendNotFoundError(BackendError):
    """Raised when backend resource is not found."""


class BackendConnectionError(BackendError):
    """Raised when backend connection fails."""


class BackendRequestError(BackendError):
    """Raised for non-auth backend errors."""


class InstaInstruClient:
    """HTTP client for InstaInstru backend API."""

    def __init__(
        self,
        settings: Settings,
        auth: MCPAuth,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.auth = auth
        self.http = http or httpx.AsyncClient(base_url=settings.api_base_url)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        request_id = str(uuid4())
        request_headers = self.auth.get_headers(request_id)
        if headers:
            request_headers.update(headers)
        try:
            response = await self.http.request(
                method,
                path,
                params=params,
                json=json,
                headers=request_headers,
            )
        except httpx.HTTPError as exc:
            raise BackendConnectionError("backend_connection_failed") from exc

        if response.status_code in {401, 403}:
            raise BackendAuthError("backend_auth_failed")
        if response.status_code == 404:
            raise BackendNotFoundError("backend_not_found")
        if response.status_code >= 400:
            raise BackendRequestError(
                f"backend_error_{response.status_code}"
            )

        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code, "text": response.text}

    async def get_funnel_summary(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/founding/funnel",
            params=params or None,
        )

    async def get_stuck_instructors(
        self,
        stuck_days: int = 7,
        stage: str | None = None,
        limit: int = 50,
    ) -> dict:
        params: dict[str, Any] = {"stuck_days": stuck_days, "limit": limit}
        if stage:
            params["stage"] = stage
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/founding/stuck",
            params=params,
        )

    async def list_instructors(self, **filters: Any) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/instructors",
            params={k: v for k, v in filters.items() if v is not None},
        )

    async def get_instructor_coverage(
        self,
        status: str = "live",
        group_by: str = "category",
        top: int = 25,
    ) -> dict:
        params = {"status": status, "group_by": group_by, "top": top}
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/instructors/coverage",
            params=params,
        )

    async def get_instructor_detail(self, identifier: str) -> dict:
        encoded_identifier = quote(identifier, safe="")
        return await self.call(
            "GET",
            f"/api/v1/admin/mcp/instructors/{encoded_identifier}",
        )

    async def preview_invites(self, **payload: Any) -> dict:
        return await self.call(
            "POST",
            "/api/v1/admin/mcp/invites/preview",
            json=payload,
        )

    async def send_invites(
        self, confirm_token: str, idempotency_key: str
    ) -> dict:
        return await self.call(
            "POST",
            "/api/v1/admin/mcp/invites/send",
            json={
                "confirm_token": confirm_token,
                "idempotency_key": idempotency_key,
            },
            headers={"Idempotency-Key": idempotency_key},
        )

    async def get_top_queries(self, **filters: Any) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/search/top-queries",
            params={k: v for k, v in filters.items() if v is not None},
        )

    async def get_zero_results(self, **filters: Any) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/search/zero-results",
            params={k: v for k, v in filters.items() if v is not None},
        )

    async def get_metric(self, metric_name: str) -> dict:
        return await self.call(
            "GET",
            f"/api/v1/admin/mcp/metrics/{metric_name}",
        )
