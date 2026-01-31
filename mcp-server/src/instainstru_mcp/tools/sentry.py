"""MCP tools for Sentry observability."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from ..clients.sentry_client import (
    SentryAuthError,
    SentryClient,
    SentryConnectionError,
    SentryNotConfiguredError,
    SentryNotFoundError,
    SentryRateLimitError,
    SentryRequestError,
)

ALLOWED_PROJECTS = {"api", "web", "mcp", "all"}
ALLOWED_ENVIRONMENTS = {"production", "preview"}
ALLOWED_TIME_RANGES = {"1h", "24h", "7d", "14d"}
ALLOWED_STATUS = {"unresolved", "resolved", "all"}
ALLOWED_SORT = {"freq", "user", "new", "date", "trends"}
ALLOWED_EVENT_TYPES = {"latest", "oldest", "recommended"}
SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key"}


def register_tools(mcp: FastMCP, sentry: SentryClient) -> dict[str, object]:
    async def instainstru_sentry_issues_top(
        project: str = "all",
        environment: str = "production",
        time_range: str = "24h",
        status: str = "unresolved",
        sort_by: str = "user",
        limit: int = 10,
        query: str | None = None,
    ) -> dict:
        """List top Sentry issues for triage."""
        try:
            _require_scope("mcp:read")
            project_key = _validate_choice("project", project, ALLOWED_PROJECTS)
            environment_key = _validate_choice("environment", environment, ALLOWED_ENVIRONMENTS)
            time_range_key = _validate_choice("time_range", time_range, ALLOWED_TIME_RANGES)
            status_key = _validate_choice("status", status, ALLOWED_STATUS)
            sort_key = _validate_choice("sort_by", sort_by, ALLOWED_SORT)
            if limit < 1 or limit > 25:
                raise ValueError("limit must be between 1 and 25")

            raw_query = query.strip() if isinstance(query, str) else None
            query_value = _build_issue_query(status_key, raw_query)

            issues = await sentry.list_issues(
                project=project_key,
                environment=environment_key,
                stats_period=time_range_key,
                status=status_key,
                sort=sort_key,
                limit=limit,
                query=query_value,
            )
            formatted = [_format_issue(issue) for issue in issues]
            total_events = sum(_safe_int(issue.get("count")) for issue in issues)
            users_affected = sum(_safe_int(issue.get("userCount")) for issue in issues)

            return {
                "summary": {
                    "issues_returned": len(formatted),
                    "total_events": total_events,
                    "users_affected": users_affected,
                    "time_range": time_range_key,
                    "environment": environment_key,
                    "note": "Totals are across returned issues only, not all issues in org",
                },
                "issues": formatted,
            }
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_sentry_issue_detail(
        issue_id: int,
        environment: str = "production",
        event: str = "recommended",
        include_stacktrace: bool = True,
        max_frames: int = 20,
    ) -> dict:
        """Fetch issue metadata and a representative event."""
        try:
            _require_scope("mcp:read")
            issue_numeric = _validate_issue_id(issue_id)
            environment_key = _validate_choice("environment", environment, ALLOWED_ENVIRONMENTS)
            event_key = _validate_choice("event", event, ALLOWED_EVENT_TYPES)
            if include_stacktrace and max_frames < 1:
                raise ValueError("max_frames must be at least 1")

            issue_data = await sentry.get_issue(issue_numeric)
            event_data = await sentry.get_issue_event(
                issue_numeric,
                event_key,
                environment=environment_key,
            )

            event_payload = _format_event(
                event_data,
                event_type=event_key,
                environment=environment_key,
                include_stacktrace=include_stacktrace,
                max_frames=max_frames,
            )

            return {
                "issue": _format_issue(issue_data),
                "event": event_payload,
            }
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    async def instainstru_sentry_event_lookup(event_id: str) -> dict:
        """Resolve a support event ID to detailed event data."""
        try:
            _require_scope("mcp:read")
            event_key = event_id.strip()
            if not event_key:
                raise ValueError("event_id is required")

            try:
                resolved = await sentry.resolve_event_id(event_key)
            except SentryNotFoundError:
                return _event_not_found(event_key)

            project_slug = resolved.get("projectSlug") or resolved.get("project_slug")
            group_id = resolved.get("groupId") or resolved.get("group_id")
            if not project_slug:
                raise ValueError("Unable to resolve project for event ID")

            event_data = await sentry.get_project_event(project_slug, event_key)
            event_payload = _format_event(
                event_data,
                event_type=None,
                environment=event_data.get("environment"),
                include_stacktrace=True,
                max_frames=None,
            )

            issue_payload = _build_issue_reference(group_id, sentry.org)
            if group_id:
                try:
                    issue_data = await sentry.get_issue(int(group_id))
                    issue_payload.update(_format_issue(issue_data))
                except (SentryNotFoundError, ValueError):
                    pass

            return {
                "found": True,
                "project": project_slug,
                "event": event_payload,
                "issue": {
                    "id": issue_payload.get("id"),
                    "short_id": issue_payload.get("short_id"),
                    "permalink": issue_payload.get("permalink"),
                },
            }
        except Exception as exc:  # pragma: no cover - handled by helper
            return _handle_error(exc)

    mcp.tool()(instainstru_sentry_issues_top)
    mcp.tool()(instainstru_sentry_issue_detail)
    mcp.tool()(instainstru_sentry_event_lookup)

    return {
        "instainstru_sentry_issues_top": instainstru_sentry_issues_top,
        "instainstru_sentry_issue_detail": instainstru_sentry_issue_detail,
        "instainstru_sentry_event_lookup": instainstru_sentry_event_lookup,
    }


def _handle_error(exc: Exception) -> dict:
    if isinstance(exc, SentryNotConfiguredError):
        return {
            "error": "sentry_not_configured",
            "message": "Sentry API token not configured.",
        }
    if isinstance(exc, SentryAuthError):
        return {"error": "sentry_auth_failed", "message": "Sentry API authentication failed."}
    if isinstance(exc, SentryRateLimitError):
        payload: dict[str, Any] = {
            "error": "sentry_rate_limited",
            "message": "Sentry API rate limit hit.",
        }
        if exc.retry_after is not None:
            payload["retry_after_seconds"] = exc.retry_after
        return payload
    if isinstance(exc, SentryNotFoundError):
        return {"error": "sentry_not_found", "message": "Sentry resource not found."}
    if isinstance(exc, SentryConnectionError):
        return {"error": "sentry_connection_failed", "message": str(exc)}
    if isinstance(exc, SentryRequestError):
        payload = {"error": "sentry_request_failed", "message": str(exc)}
        if exc.status_code is not None:
            payload["status_code"] = exc.status_code
        return payload
    if isinstance(exc, PermissionError):
        return {"error": "insufficient_scope", "message": str(exc)}
    if isinstance(exc, ValueError):
        return {"error": "invalid_request", "message": str(exc)}
    return {"error": "unknown_error", "message": str(exc)}


def _validate_choice(name: str, value: str, allowed: set[str]) -> str:
    key = value.strip().lower()
    if key not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise ValueError(f"Invalid {name}: {value}. Allowed: {allowed_list}.")
    return key


def _validate_issue_id(issue_id: int | str) -> int:
    if isinstance(issue_id, int):
        return issue_id
    if isinstance(issue_id, str) and issue_id.isdigit():
        return int(issue_id)
    raise ValueError("issue_id must be a numeric Sentry issue ID")


def _build_issue_query(status: str, query: str | None) -> str | None:
    status_filter = None
    if status == "unresolved":
        status_filter = "is:unresolved"
    elif status == "resolved":
        status_filter = "is:resolved"

    if status_filter and query:
        return f"{status_filter} {query}".strip()
    if status_filter:
        return status_filter
    return query or None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_issue(issue: dict[str, Any]) -> dict[str, Any]:
    project = issue.get("project")
    project_slug = project.get("slug") if isinstance(project, dict) else project
    issue_id = issue.get("id")
    issue_id_value = _safe_int(issue_id) if issue_id is not None else None
    return {
        "id": issue_id_value if issue_id_value != 0 else issue_id,
        "short_id": issue.get("shortId") or issue.get("short_id"),
        "title": issue.get("title"),
        "project": project_slug,
        "culprit": issue.get("culprit"),
        "count": _safe_int(issue.get("count")),
        "user_count": _safe_int(issue.get("userCount")),
        "first_seen": issue.get("firstSeen"),
        "last_seen": issue.get("lastSeen"),
        "level": issue.get("level"),
        "status": issue.get("status"),
        "permalink": issue.get("permalink"),
    }


def _format_event(
    event: dict[str, Any],
    *,
    event_type: str | None,
    environment: str | None,
    include_stacktrace: bool,
    max_frames: int | None,
) -> dict[str, Any]:
    tags = _normalize_tags(event.get("tags"))
    user = _redact_user(event.get("user"))
    request = _extract_request(event.get("request"))
    stacktrace = None
    if include_stacktrace:
        stacktrace = _extract_stacktrace(event, max_frames=max_frames)

    payload: dict[str, Any] = {
        "id": event.get("eventID") or event.get("id"),
        "title": event.get("title") or event.get("message"),
        "message": _extract_message(event),
        "timestamp": event.get("dateCreated") or event.get("timestamp"),
        "environment": event.get("environment") or environment,
        "release": event.get("release"),
        "tags": tags,
        "user": user,
        "request": request,
    }
    if event_type is not None:
        payload["event_type"] = event_type
    if include_stacktrace:
        payload["stacktrace"] = stacktrace
    return payload


def _extract_message(event: dict[str, Any]) -> str | None:
    message = event.get("message")
    if isinstance(message, str) and message:
        return message
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        log_message = logentry.get("message") or logentry.get("formatted")
        if isinstance(log_message, str) and log_message:
            return log_message
    return None


def _normalize_tags(tags: Any) -> dict[str, Any]:
    if isinstance(tags, dict):
        return tags
    if isinstance(tags, list):
        normalized: dict[str, Any] = {}
        for item in tags:
            key = None
            value = None
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                key, value = item[0], item[1]
            elif isinstance(item, dict):
                key = item.get("key")
                value = item.get("value")
            if key is not None:
                normalized[str(key)] = value
        return normalized
    return {}


def _redact_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _redact_user(user: Any) -> dict[str, Any] | None:
    if not isinstance(user, dict):
        return None
    email = _redact_email(user.get("email"))
    user_id = user.get("id") or user.get("user")
    payload: dict[str, Any] = {}
    if user_id is not None:
        payload["id"] = user_id
    if email is not None:
        payload["email"] = email
    return payload or None


def _normalize_headers(headers: Any) -> dict[str, Any]:
    if isinstance(headers, dict):
        return dict(headers)
    if isinstance(headers, list):
        normalized: dict[str, Any] = {}
        for item in headers:
            key = None
            value = None
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                key, value = item[0], item[1]
            elif isinstance(item, dict):
                key = item.get("key") or item.get("name")
                value = item.get("value")
            if key is not None:
                normalized[str(key)] = value
        return normalized
    return {}


def _redact_headers(headers: Any) -> dict[str, Any]:
    normalized = _normalize_headers(headers)
    redacted: dict[str, Any] = {}
    for key, value in normalized.items():
        if str(key).lower() in SENSITIVE_HEADERS:
            continue
        redacted[key] = value
    return redacted


def _extract_request(request: Any) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return None
    payload: dict[str, Any] = {}
    method = request.get("method")
    url = request.get("url")
    if method:
        payload["method"] = method
    if url:
        payload["url"] = url
    headers = request.get("headers")
    if headers is not None:
        payload["headers"] = _redact_headers(headers)
    return payload or None


def _extract_stacktrace(event: dict[str, Any], max_frames: int | None) -> str:
    frames = _find_stacktrace_frames(event)
    if max_frames is not None and max_frames > 0 and len(frames) > max_frames:
        frames = frames[-max_frames:]
    lines: list[str] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        filename = frame.get("filename") or frame.get("abs_path") or frame.get("module")
        lineno = frame.get("lineno")
        function = frame.get("function") or frame.get("name")
        if filename is None:
            filename = "<unknown>"
        line = f'File "{filename}"'
        if lineno is not None:
            line += f", line {lineno}"
        if function:
            line += f", in {function}"
        lines.append(line)
        context_line = frame.get("context_line")
        if context_line:
            lines.append(f"    {context_line}")
    return "\n".join(lines)


def _find_stacktrace_frames(event: dict[str, Any]) -> list[Any]:
    entries = event.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "exception":
                data = entry.get("data") or {}
                values = data.get("values") or []
                if isinstance(values, list):
                    for exc in reversed(values):
                        if not isinstance(exc, dict):
                            continue
                        stacktrace = exc.get("stacktrace") or {}
                        frames = stacktrace.get("frames")
                        if isinstance(frames, list):
                            return frames
            if entry.get("type") == "stacktrace":
                data = entry.get("data") or {}
                frames = data.get("frames")
                if isinstance(frames, list):
                    return frames
    return []


def _build_issue_reference(group_id: Any, org: str) -> dict[str, Any]:
    issue_id = None
    try:
        if group_id is not None:
            issue_id = int(group_id)
    except (TypeError, ValueError):
        issue_id = group_id
    permalink = None
    if issue_id is not None:
        permalink = f"https://sentry.io/organizations/{org}/issues/{issue_id}/"
    return {"id": issue_id, "short_id": None, "permalink": permalink}


def _event_not_found(event_id: str) -> dict:
    return {
        "found": False,
        "event_id": event_id,
        "reason": "Event ID not found in Sentry",
        "suggestions": [
            "Event may have been dropped by inbound filters or rate limits",
            "Event may still be processing (try again in 1-2 minutes)",
            "Verify the event ID was copied correctly",
        ],
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
