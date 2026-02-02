"""
Deploy Overview - Show what's running on each service.

Aggregates health/version info from all InstaInstru services.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

SERVICES = {
    "production": {
        "api": "https://api.instainstru.com",
        "mcp": "https://mcp.instainstru.com",
        "web": "https://instainstru.com",
    },
    "preview": {
        "api": "https://preview-api.instainstru.com",
        "mcp": "https://preview-mcp.instainstru.com",
        "web": "https://preview.instainstru.com",
    },
}

HEALTH_PATHS = {
    "api": "/api/v1/health",
    "mcp": "/health",
    "web": "/api/health",
}


def _require_scope(required_scope: str) -> None:
    request = get_http_request()
    auth = getattr(request, "scope", {}).get("auth", {})
    method = auth.get("method") if isinstance(auth, dict) else None
    if method == "simple_token":
        return
    claims = auth.get("claims", {}) if isinstance(auth, dict) else {}
    scope_value = ""
    if isinstance(claims, dict):
        scope_value = claims.get("scope") or claims.get("scp") or ""
    if not scope_value and isinstance(auth, dict):
        scope_value = auth.get("scope") or ""
    scopes = {scope for scope in scope_value.split() if scope}
    if required_scope not in scopes:
        if required_scope == "mcp:read" and method in {"jwt", "workos"}:
            return
        raise PermissionError(f"Missing required scope: {required_scope}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _check_service(
    http: httpx.AsyncClient,
    name: str,
    base_url: str,
    health_path: str,
) -> dict[str, Any]:
    """Check a single service's health endpoint."""
    url = f"{base_url}{health_path}"
    start = _utc_now()

    try:
        response = await http.get(url, timeout=10.0)
        elapsed_ms = (_utc_now() - start).total_seconds() * 1000

        result: dict[str, Any] = {
            "status": "up" if response.status_code == 200 else "degraded",
            "url": base_url,
            "response_time_ms": round(elapsed_ms, 1),
            "checked_at": _utc_now().isoformat(),
            "http_status": response.status_code,
        }

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception:
                data = None
            if isinstance(data, dict):
                if "git_sha" in data:
                    result["git_sha"] = data["git_sha"]
                if "version" in data:
                    result["version"] = data["version"]
                if "uptime_seconds" in data:
                    result["uptime_seconds"] = data["uptime_seconds"]
                elif "uptime" in data:
                    result["uptime_seconds"] = data["uptime"]
                if "commit" in data:
                    result["git_sha"] = data["commit"]

        return result

    except httpx.TimeoutException:
        return {
            "status": "down",
            "url": base_url,
            "error": "timeout",
            "checked_at": _utc_now().isoformat(),
        }
    except Exception as exc:
        return {
            "status": "down",
            "url": base_url,
            "error": str(exc),
            "checked_at": _utc_now().isoformat(),
        }


async def _check_environment(
    http: httpx.AsyncClient,
    env: str,
    services: dict[str, str],
) -> dict[str, Any]:
    """Check all services in an environment."""
    tasks = [
        _check_service(http, name, url, HEALTH_PATHS.get(name, "/health"))
        for name, url in services.items()
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    service_results: dict[str, Any] = {}
    for (name, url), result in zip(services.items(), results):
        if isinstance(result, Exception):
            service_results[name] = {
                "status": "down",
                "url": url,
                "error": str(result),
                "checked_at": _utc_now().isoformat(),
            }
        else:
            service_results[name] = result

    statuses = [service.get("status") for service in service_results.values()]
    if statuses and all(status == "up" for status in statuses):
        env_status = "ok"
    elif statuses and all(status == "down" for status in statuses):
        env_status = "down"
    else:
        env_status = "degraded"

    return {
        "status": env_status,
        "services": service_results,
    }


def _detect_version_drift(environments: dict[str, Any]) -> dict[str, Any]:
    """Check if services are running different git SHAs."""
    shas: dict[str, str] = {}
    for env_name, env_data in environments.items():
        for svc_name, svc_data in env_data.get("services", {}).items():
            sha = svc_data.get("git_sha")
            if sha:
                key = f"{env_name}/{svc_name}"
                shas[key] = sha

    unique_shas = set(shas.values())
    if len(unique_shas) <= 1:
        return {"detected": False, "details": None}

    return {
        "detected": True,
        "details": shas,
        "note": "Services running different commits",
    }


def register_tools(mcp: FastMCP) -> dict[str, object]:
    async def instainstru_deploy_overview(
        env: str = "production",
        include_preview: bool = False,
    ) -> dict:
        """
        Show what's deployed across all InstaInstru services.

        Returns for each service:
        - status: up/down/degraded
        - git_sha: commit hash (if exposed in health endpoint)
        - version: semantic version (if available)
        - uptime: how long service has been running
        - response_time_ms: health check latency
        - url: service base URL

        Args:
            env: Environment to check ("production" or "preview")
            include_preview: If True and env="production", also check preview
        """
        _require_scope("mcp:read")

        env_value = (env or "production").strip().lower()
        if env_value not in SERVICES:
            raise ValueError("env must be 'production' or 'preview'")

        environments_to_check = [env_value]
        if include_preview and env_value == "production":
            environments_to_check.append("preview")

        environments: dict[str, Any] = {}
        async with httpx.AsyncClient() as http:
            checks = await asyncio.gather(
                *[_check_environment(http, name, SERVICES[name]) for name in environments_to_check]
            )

        for name, payload in zip(environments_to_check, checks):
            environments[name] = payload

        services_checked = 0
        services_up = 0
        services_down = 0
        response_times: list[float] = []

        for env_data in environments.values():
            for service in env_data.get("services", {}).values():
                services_checked += 1
                status = service.get("status")
                if status == "up":
                    services_up += 1
                elif status == "down":
                    services_down += 1
                response_time = service.get("response_time_ms")
                if isinstance(response_time, (int, float)):
                    response_times.append(float(response_time))

        avg_response_time = (
            round(sum(response_times) / len(response_times), 1) if response_times else None
        )

        summary = {
            "all_services_up": services_checked > 0 and services_up == services_checked,
            "services_checked": services_checked,
            "services_up": services_up,
            "services_down": services_down,
            "avg_response_time_ms": avg_response_time,
        }

        return {
            "meta": {
                "generated_at": _utc_now().isoformat(),
                "environments_checked": environments_to_check,
            },
            "environments": environments,
            "summary": summary,
            "version_drift": _detect_version_drift(environments),
        }

    mcp.tool()(instainstru_deploy_overview)
    return {"instainstru_deploy_overview": instainstru_deploy_overview}


__all__ = [
    "SERVICES",
    "HEALTH_PATHS",
    "_check_service",
    "_check_environment",
    "_detect_version_drift",
    "register_tools",
]
