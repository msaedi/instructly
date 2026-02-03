"""HTTP client for the InstaInstru backend MCP endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
from pydantic import SecretStr

from .auth import AuthenticationError, MCPAuth
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


class TokenCache:
    """Cache for M2M access tokens."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def get(self) -> str | None:
        if self._token and self._expires_at:
            now = datetime.now(timezone.utc)
            if now < (self._expires_at - timedelta(seconds=60)):
                return self._token
        return None

    def set(self, token: str, expires_in: int) -> None:
        now = datetime.now(timezone.utc)
        self._token = token
        self._expires_at = now + timedelta(seconds=expires_in)


logger = logging.getLogger(__name__)


def _secret_value(value: SecretStr | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)


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
        self._token_cache = TokenCache()
        self.http = http or httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=30.0,
                write=10.0,
                pool=10.0,
            ),
        )

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
        timeout: float | httpx.Timeout | None = None,
    ) -> dict:
        request_id = str(uuid4())
        request_headers = self.auth.get_headers(request_id)
        token = await self._get_bearer_token()
        request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)
        try:
            response = await self.http.request(
                method,
                path,
                params=params,
                json=json,
                headers=request_headers,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            timeout_value: float | None = None
            if isinstance(timeout, (int, float)):
                timeout_value = float(timeout)
            elif isinstance(timeout, httpx.Timeout):
                timeout_value = timeout.read
            else:
                timeout_value = self.http.timeout.read
            if timeout_value is not None:
                message = f"backend_timeout: Request to {path} timed out after {timeout_value}s"
            else:
                message = f"backend_timeout: Request to {path} timed out"
            raise BackendConnectionError(message) from exc
        except httpx.HTTPError as exc:
            raise BackendConnectionError(f"backend_connection_failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise BackendAuthError("backend_auth_failed")
        if response.status_code == 404:
            raise BackendNotFoundError("backend_not_found")
        if response.status_code >= 400:
            raise BackendRequestError(f"backend_error_{response.status_code}")

        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code, "text": response.text}

    async def _get_bearer_token(self) -> str:
        if self._m2m_configured():
            try:
                return await self._get_access_token()
            except Exception as exc:
                static_token = self._get_static_token()
                if static_token:
                    logger.warning("m2m_token_fetch_failed_fallback_static", exc_info=exc)
                    return static_token
                raise BackendConnectionError("m2m_token_fetch_failed") from exc
        static_token = self._get_static_token()
        if static_token:
            return static_token
        raise AuthenticationError("api_service_token_missing")

    def _m2m_configured(self) -> bool:
        return bool(
            self.settings.workos_m2m_client_id
            and _secret_value(self.settings.workos_m2m_client_secret).strip()
            and self.settings.workos_m2m_token_url
            and self.settings.workos_m2m_audience
        )

    def _get_static_token(self) -> str:
        return _secret_value(self.settings.api_service_token).strip()

    async def _get_access_token(self) -> str:
        cached = self._token_cache.get()
        if cached:
            return cached

        client_secret = _secret_value(self.settings.workos_m2m_client_secret).strip()
        if not self.settings.workos_m2m_client_id or not client_secret:
            raise BackendConnectionError("m2m_client_credentials_missing")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self.settings.workos_m2m_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.workos_m2m_client_id,
                    "client_secret": client_secret,
                    "audience": self.settings.workos_m2m_audience,
                    "scope": "mcp:read mcp:write",
                },
            )
            response.raise_for_status()
            data = response.json()

        token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_cache.set(token, expires_in)
        return token

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
            timeout=60.0,
        )

    async def send_invites(self, confirm_token: str, idempotency_key: str) -> dict:
        return await self.call(
            "POST",
            "/api/v1/admin/mcp/invites/send",
            json={
                "confirm_token": confirm_token,
                "idempotency_key": idempotency_key,
            },
            headers={"Idempotency-Key": idempotency_key},
        )

    async def list_invites(self, **filters: Any) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/invites",
            params={k: v for k, v in filters.items() if v is not None},
        )

    async def get_invite_detail(self, identifier: str) -> dict:
        encoded = quote(identifier, safe="")
        return await self.call(
            "GET",
            f"/api/v1/admin/mcp/invites/{encoded}",
        )

    async def get_services_catalog(self) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/services/catalog",
        )

    async def lookup_service(self, query: str) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/services/lookup",
            params={"q": query},
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

    async def get_celery_workers(self) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/celery/workers",
        )

    async def get_celery_queues(self) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/celery/queues",
        )

    async def get_celery_failed_tasks(self, limit: int = 50) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/celery/failed",
            params={"limit": limit},
        )

    async def get_celery_payment_health(self) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/celery/payment-health",
        )

    # Tier 2 Celery endpoints

    async def get_celery_active_tasks(self) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/celery/tasks/active",
        )

    async def get_celery_task_history(
        self,
        task_name: str | None = None,
        state: str | None = None,
        hours: int = 1,
        limit: int = 100,
    ) -> dict:
        params: dict[str, Any] = {"hours": hours, "limit": limit}
        if task_name:
            params["task_name"] = task_name
        if state:
            params["state"] = state
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/celery/tasks/history",
            params=params,
        )

    async def get_celery_beat_schedule(self) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/celery/schedule",
        )

    # ==================== Operations endpoints ====================

    async def get_booking_summary(self, period: str = "today") -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/ops/bookings/summary",
            params={"period": period},
        )

    async def get_recent_bookings(
        self,
        status: str | None = None,
        limit: int = 20,
        hours: int = 24,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "hours": hours}
        if status:
            params["status"] = status
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/ops/bookings/recent",
            params=params,
        )

    async def get_payment_pipeline(self) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/ops/payments/pipeline",
        )

    async def get_pending_payouts(self, limit: int = 20) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/ops/payments/pending-payouts",
            params={"limit": limit},
        )

    async def lookup_user(self, identifier: str) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/ops/users/lookup",
            params={"identifier": identifier},
        )

    async def get_user_booking_history(self, user_id: str, limit: int = 20) -> dict:
        return await self.call(
            "GET",
            f"/api/v1/admin/mcp/ops/users/{user_id}/bookings",
            params={"limit": limit},
        )

    async def get_webhooks(
        self,
        *,
        source: str | None = None,
        status: str | None = None,
        event_type: str | None = None,
        since_hours: int = 24,
        limit: int = 50,
    ) -> dict:
        params: dict[str, Any] = {"since_hours": since_hours, "limit": limit}
        if source:
            params["source"] = source
        if status:
            params["status"] = status
        if event_type:
            params["event_type"] = event_type
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/webhooks",
            params=params,
        )

    async def get_failed_webhooks(
        self,
        *,
        source: str | None = None,
        since_hours: int = 24,
        limit: int = 50,
    ) -> dict:
        params: dict[str, Any] = {"since_hours": since_hours, "limit": limit}
        if source:
            params["source"] = source
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/webhooks/failed",
            params=params,
        )

    async def get_webhook_detail(self, event_id: str) -> dict:
        return await self.call(
            "GET",
            f"/api/v1/admin/mcp/webhooks/{quote(event_id)}",
        )

    async def replay_webhook(self, event_id: str, dry_run: bool = True) -> dict:
        return await self.call(
            "POST",
            f"/api/v1/admin/mcp/webhooks/{quote(event_id)}/replay",
            params={"dry_run": dry_run},
        )

    # ==================== Audit endpoints ====================

    async def audit_search(self, **filters: Any) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/audit/search",
            params={k: v for k, v in filters.items() if v is not None},
        )

    async def audit_user_activity(
        self, user_email: str, since_days: int = 30, limit: int = 100
    ) -> dict:
        return await self.call(
            "GET",
            f"/api/v1/admin/mcp/audit/users/{quote(user_email)}/activity",
            params={"since_days": since_days, "limit": limit},
        )

    async def audit_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 50,
    ) -> dict:
        return await self.call(
            "GET",
            f"/api/v1/admin/mcp/audit/resources/{quote(resource_type)}/{quote(resource_id)}/history",
            params={"limit": limit},
        )

    async def audit_recent_admin_actions(self, since_hours: int = 24, limit: int = 100) -> dict:
        return await self.call(
            "GET",
            "/api/v1/admin/mcp/audit/admin-actions/recent",
            params={"since_hours": since_hours, "limit": limit},
        )
