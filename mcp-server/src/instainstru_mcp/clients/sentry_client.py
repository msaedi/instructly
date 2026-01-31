"""HTTP client for Sentry APIs."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import SecretStr


class SentryClientError(Exception):
    """Base error for Sentry API failures."""


class SentryNotConfiguredError(SentryClientError):
    """Raised when Sentry settings are missing."""


class SentryAuthError(SentryClientError):
    """Raised when Sentry rejects authentication."""


class SentryNotFoundError(SentryClientError):
    """Raised when a Sentry resource is not found."""


class SentryRateLimitError(SentryClientError):
    """Raised when Sentry API rate limits requests."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class SentryConnectionError(SentryClientError):
    """Raised when Sentry cannot be reached."""


class SentryRequestError(SentryClientError):
    """Raised for non-auth Sentry errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _secret_value(value: SecretStr | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _decode_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


def _extract_error_message(response: httpx.Response) -> str:
    payload = _decode_response(response)
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or payload.get("message")
        if isinstance(detail, str) and detail:
            return detail
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                message = first.get("message") or first.get("detail")
                if isinstance(message, str) and message:
                    return message
    if isinstance(payload, list) and payload:
        if isinstance(payload[0], str):
            return payload[0]
    return response.text or "sentry_request_failed"


class SentryClient:
    """Client for Sentry API."""

    BASE_URL = "https://sentry.io/api/0"

    PROJECT_SLUGS = {
        "api": "instainstru-api",
        "web": "instainstru-web",
        "mcp": "instainstru-mcp",
    }

    def __init__(
        self,
        token: SecretStr | str,
        org: str = "instainstru",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.org = org
        self.http = http or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(
                connect=10.0,
                read=30.0,
                write=10.0,
                pool=10.0,
            ),
        )
        self._project_ids: dict[str, int] | None = None
        self._project_ids_fetched_at: datetime | None = None
        self._issues_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}

    async def aclose(self) -> None:
        await self.http.aclose()

    @property
    def configured(self) -> bool:
        return bool(_secret_value(self.token).strip())

    def _auth_header(self) -> dict[str, str]:
        token = _secret_value(self.token).strip()
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if not self.configured:
            raise SentryNotConfiguredError("sentry_not_configured")

        request_headers = {"Accept": "application/json", **self._auth_header()}
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
        except httpx.TimeoutException as exc:
            raise SentryConnectionError("sentry_timeout") from exc
        except httpx.HTTPError as exc:
            raise SentryConnectionError(f"sentry_connection_failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise SentryAuthError("sentry_auth_failed")
        if response.status_code == 404:
            raise SentryNotFoundError("sentry_not_found")
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise SentryRateLimitError("sentry_rate_limited", retry_after=retry_after)
        if response.status_code >= 400:
            message = _extract_error_message(response)
            raise SentryRequestError(message, status_code=response.status_code)

        return _decode_response(response)

    async def _get_project_ids(self) -> dict[str, int]:
        """Get slug -> ID mapping, cached for 24 hours."""
        now = datetime.now(timezone.utc)
        if self._project_ids and self._project_ids_fetched_at:
            if now - self._project_ids_fetched_at < timedelta(hours=24):
                return self._project_ids

        data = await self._request("GET", f"/organizations/{self.org}/projects/")
        project_ids: dict[str, int] = {}
        for project in data or []:
            if not isinstance(project, dict):
                continue
            slug = project.get("slug")
            project_id = project.get("id")
            if slug and project_id is not None:
                try:
                    project_ids[str(slug)] = int(project_id)
                except (TypeError, ValueError):
                    continue

        self._project_ids = project_ids
        self._project_ids_fetched_at = now
        return project_ids

    async def _resolve_project_param(self, project: str) -> int:
        project_key = project.strip().lower()
        if project_key == "all":
            return -1
        slug = self.PROJECT_SLUGS.get(project_key)
        if not slug:
            raise ValueError(f"Unknown project: {project}")
        project_ids = await self._get_project_ids()
        project_id = project_ids.get(slug)
        if project_id is None:
            raise ValueError(f"Project ID not found for slug: {slug}")
        return project_id

    def _issues_cache_key(
        self,
        *,
        project: str,
        environment: str,
        stats_period: str,
        status: str,
        sort: str,
        limit: int,
        query: str | None,
    ) -> str:
        digest = hashlib.sha256((query or "").encode("utf-8")).hexdigest()
        query_hash = digest[:12]
        return f"sentry:issues:{project}:{environment}:{stats_period}:{status}:{sort}:{limit}:{query_hash}"

    def _get_cached_issues(self, cache_key: str) -> list[dict[str, Any]] | None:
        cached = self._issues_cache.get(cache_key)
        if not cached:
            return None
        expires_at, payload = cached
        if datetime.now(timezone.utc) >= expires_at:
            self._issues_cache.pop(cache_key, None)
            return None
        return payload

    def _set_cached_issues(self, cache_key: str, payload: list[dict[str, Any]]) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
        self._issues_cache[cache_key] = (expires_at, payload)

    async def list_issues(
        self,
        *,
        project: str,
        environment: str,
        stats_period: str,
        status: str,
        sort: str,
        limit: int,
        query: str | None,
    ) -> list[dict[str, Any]]:
        cache_key = self._issues_cache_key(
            project=project,
            environment=environment,
            stats_period=stats_period,
            status=status,
            sort=sort,
            limit=limit,
            query=query,
        )
        cached = self._get_cached_issues(cache_key)
        if cached is not None:
            return cached

        project_param = await self._resolve_project_param(project)
        params: dict[str, Any] = {
            "project": project_param,
            "environment": environment,
            "statsPeriod": stats_period,
            "sort": sort,
            "per_page": limit,
        }
        if query:
            params["query"] = query

        data = await self._request("GET", f"/organizations/{self.org}/issues/", params=params)
        issues = data if isinstance(data, list) else []
        self._set_cached_issues(cache_key, issues)
        return issues

    async def get_issue(self, issue_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"/organizations/{self.org}/issues/{issue_id}/")
        return data if isinstance(data, dict) else {}

    async def get_issue_event(
        self,
        issue_id: int,
        event_type: str,
        *,
        environment: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if environment:
            params["environment"] = environment
        data = await self._request(
            "GET",
            f"/organizations/{self.org}/issues/{issue_id}/events/{event_type}/",
            params=params or None,
        )
        return data if isinstance(data, dict) else {}

    async def resolve_event_id(self, event_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/organizations/{self.org}/eventids/{event_id}/",
        )
        return data if isinstance(data, dict) else {}

    async def get_project_event(self, project_slug: str, event_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/projects/{self.org}/{project_slug}/events/{event_id}/",
        )
        return data if isinstance(data, dict) else {}
