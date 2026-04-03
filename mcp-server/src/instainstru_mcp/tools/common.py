"""Shared helpers for MCP tools."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Literal, Optional, ParamSpec, Tuple

from fastmcp import FastMCP

from ..client import BackendNotFoundError

P = ParamSpec("P")


def _parse_rfc3339(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def resolve_time_window(
    since_hours: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    default_hours: int = 24,
) -> Tuple[datetime, datetime, str]:
    """
    Resolve time window from flexible inputs.

    Priority:
    1. If start_time provided, use it (with end_time or now)
    2. Else use since_hours (or default_hours)

    Returns (start_dt, end_dt, source) as UTC datetimes.
    """
    now = datetime.now(timezone.utc)

    if start_time:
        start_dt = _parse_rfc3339(start_time)
        if end_time:
            end_dt = _parse_rfc3339(end_time)
            source = f"start_time={start_time},end_time={end_time}"
        else:
            end_dt = now
            source = f"start_time={start_time},end_time=now"
        if end_dt < start_dt:
            raise ValueError("end_time must be on or after start_time")
        return start_dt, end_dt, source

    if end_time and not start_time:
        raise ValueError("start_time must be provided when end_time is set")

    try:
        normalized_hours = int(since_hours if since_hours is not None else default_hours)
    except (TypeError, ValueError):
        normalized_hours = default_hours
    if normalized_hours < 1:
        normalized_hours = 1

    start_dt = now - timedelta(hours=normalized_hours)
    return start_dt, now, f"since_hours={normalized_hours}"


def build_not_found_response(
    *,
    mode: Literal["read", "write"],
    error: str = "backend_not_found",
    message: str = "Requested resource was not found.",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any]
    if mode == "write":
        response = {"success": False, "error": error, "message": message}
    else:
        response = {"found": False, "error": error, "message": message}
    if extra:
        response.update(extra)
    return response


def register_backend_tool(
    mcp: FastMCP,
    func: Callable[P, Coroutine[Any, Any, dict[str, Any]]],
    *,
    mode: Literal["read", "write"] = "read",
    error: str = "backend_not_found",
    message: str = "Requested resource was not found.",
    extra: dict[str, Any] | None = None,
    on_not_found: Callable[P, dict[str, Any]] | None = None,
) -> Callable[P, Coroutine[Any, Any, dict[str, Any]]]:
    @wraps(func)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)
        except BackendNotFoundError:
            if on_not_found is not None:
                return on_not_found(*args, **kwargs)
            return build_not_found_response(
                mode=mode,
                error=error,
                message=message,
                extra=extra,
            )

    mcp.tool()(wrapped)
    return wrapped
