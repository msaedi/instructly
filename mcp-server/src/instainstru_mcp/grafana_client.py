"""HTTP client for Grafana Cloud APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import SecretStr

from .config import Settings

logger = logging.getLogger(__name__)


class GrafanaClientError(Exception):
    """Base error for Grafana API failures."""


class GrafanaNotConfiguredError(GrafanaClientError):
    """Raised when Grafana Cloud settings are missing."""


class GrafanaAuthError(GrafanaClientError):
    """Raised when Grafana rejects authentication."""


class GrafanaNotFoundError(GrafanaClientError):
    """Raised when a Grafana resource is not found."""


class GrafanaRateLimitError(GrafanaClientError):
    """Raised when Grafana API rate limits requests."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class GrafanaConnectionError(GrafanaClientError):
    """Raised when Grafana cannot be reached."""


class GrafanaRequestError(GrafanaClientError):
    """Raised for non-auth Grafana errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _secret_value(value: SecretStr | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)


class GrafanaCloudClient:
    """Client for Grafana Cloud API."""

    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.http = http or httpx.AsyncClient(
            base_url=settings.grafana_cloud_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=30.0,
                write=10.0,
                pool=10.0,
            ),
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.grafana_cloud_url.strip()
            and _secret_value(self.settings.grafana_cloud_api_key).strip()
        )

    def _auth_header(self) -> dict[str, str]:
        token = _secret_value(self.settings.grafana_cloud_api_key).strip()
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
            raise GrafanaNotConfiguredError("grafana_not_configured")

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
            raise GrafanaConnectionError("grafana_timeout") from exc
        except httpx.HTTPError as exc:
            raise GrafanaConnectionError(f"grafana_connection_failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise GrafanaAuthError("grafana_auth_failed")
        if response.status_code == 404:
            raise GrafanaNotFoundError("grafana_not_found")
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise GrafanaRateLimitError("grafana_rate_limited", retry_after=retry_after)
        if response.status_code >= 400:
            message = _extract_error_message(response)
            raise GrafanaRequestError(message, status_code=response.status_code)

        return _decode_response(response)

    async def query_prometheus(self, query: str, time: str | None = None) -> dict:
        """Execute PromQL instant query."""
        params: dict[str, Any] = {"query": query}
        if time:
            params["time"] = time
        data = await self._request(
            "GET",
            f"/api/datasources/proxy/uid/{self.settings.grafana_prometheus_datasource_uid}/api/v1/query",
            params=params,
        )
        _raise_if_prometheus_error(data)
        result = data.get("data", {})
        return {
            "query": query,
            "result_type": result.get("resultType"),
            "results": _format_prometheus_results(result),
            "warnings": data.get("warnings", []),
        }

    async def query_prometheus_range(
        self,
        query: str,
        start: str,
        end: str,
        step: str = "60s",
    ) -> dict:
        """Execute PromQL range query."""
        params: dict[str, Any] = {"query": query, "start": start, "end": end, "step": step}
        data = await self._request(
            "GET",
            f"/api/datasources/proxy/uid/{self.settings.grafana_prometheus_datasource_uid}/api/v1/query_range",
            params=params,
        )
        _raise_if_prometheus_error(data)
        result = data.get("data", {})
        return {
            "query": query,
            "result_type": result.get("resultType"),
            "results": _format_prometheus_results(result),
            "warnings": data.get("warnings", []),
        }

    async def list_dashboards(self) -> list[dict[str, Any]]:
        """List Grafana dashboards."""
        data = await self._request("GET", "/api/search", params={"type": "dash-db"})
        dashboards = []
        for item in data or []:
            dashboards.append(
                {
                    "uid": item.get("uid"),
                    "title": item.get("title"),
                    "folder": item.get("folderTitle"),
                    "folder_uid": item.get("folderUid"),
                    "url": item.get("url"),
                    "id": item.get("id"),
                }
            )
        return dashboards

    async def get_dashboard(self, uid: str) -> dict[str, Any]:
        """Get dashboard metadata by UID."""
        data = await self._request("GET", f"/api/dashboards/uid/{uid}")
        dashboard = data.get("dashboard", {}) if isinstance(data, dict) else {}
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        return {
            "uid": dashboard.get("uid"),
            "title": dashboard.get("title"),
            "timezone": dashboard.get("timezone"),
            "schema_version": dashboard.get("schemaVersion"),
            "tags": dashboard.get("tags", []),
            "panels": dashboard.get("panels", []),
            "templating": dashboard.get("templating", {}),
            "meta": {
                "folder": meta.get("folderTitle"),
                "folder_uid": meta.get("folderUid"),
                "slug": meta.get("slug"),
            },
        }

    async def list_alerts(self, state: str | None = None) -> list[dict[str, Any]]:
        """List Grafana alerts."""
        data = await self._request("GET", "/api/alertmanager/grafana/api/v2/alerts")
        alerts = []
        for alert in data or []:
            alert_state = (alert.get("status") or {}).get("state")
            if state and alert_state != state:
                continue
            alerts.append(
                {
                    "name": (alert.get("labels") or {}).get("alertname"),
                    "state": alert_state,
                    "labels": alert.get("labels", {}),
                    "annotations": alert.get("annotations", {}),
                    "starts_at": alert.get("startsAt"),
                    "ends_at": alert.get("endsAt"),
                    "generator_url": alert.get("generatorURL"),
                }
            )
        return alerts

    async def create_silence(
        self,
        matchers: list[dict[str, Any]],
        duration_minutes: int,
        comment: str,
        created_by: str,
    ) -> dict[str, Any]:
        """Create alert silence."""
        if duration_minutes > 1440:
            raise GrafanaRequestError("silence_duration_exceeds_24h")
        now = datetime.now(timezone.utc)
        end_time = now + timedelta(minutes=duration_minutes)
        payload = {
            "matchers": matchers,
            "startsAt": now.isoformat(),
            "endsAt": end_time.isoformat(),
            "createdBy": created_by,
            "comment": comment,
        }
        data = await self._request(
            "POST",
            "/api/alertmanager/grafana/api/v2/silences",
            json=payload,
        )
        return {
            "silence_id": data.get("silenceID") if isinstance(data, dict) else None,
            "starts_at": payload["startsAt"],
            "ends_at": payload["endsAt"],
        }

    async def list_silences(self, active_only: bool = True) -> list[dict[str, Any]]:
        """List alert silences."""
        data = await self._request("GET", "/api/alertmanager/grafana/api/v2/silences")
        silences = []
        for silence in data or []:
            status = silence.get("status", {})
            state = status.get("state")
            if active_only and state != "active":
                continue
            silences.append(
                {
                    "id": silence.get("id"),
                    "status": state,
                    "matchers": silence.get("matchers", []),
                    "starts_at": silence.get("startsAt"),
                    "ends_at": silence.get("endsAt"),
                    "comment": silence.get("comment"),
                    "created_by": silence.get("createdBy"),
                }
            )
        return silences

    async def delete_silence(self, silence_id: str) -> bool:
        """Delete/expire a silence."""
        await self._request(
            "DELETE",
            f"/api/alertmanager/grafana/api/v2/silence/{silence_id}",
        )
        return True


def _decode_response(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"status_code": response.status_code, "text": response.text}


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or payload.get("errorMessage")
            if message:
                return str(message)
    except ValueError:
        pass
    return f"grafana_error_{response.status_code}"


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    return None


def _raise_if_prometheus_error(payload: Any) -> None:
    if isinstance(payload, dict) and payload.get("status") == "error":
        message = payload.get("error") or "prometheus_query_error"
        raise GrafanaRequestError(str(message))


def _format_prometheus_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in result.get("result", []) if isinstance(result, dict) else []:
        results.append(
            {
                "metric": item.get("metric", {}),
                "value": item.get("value"),
                "values": item.get("values"),
            }
        )
    return results
