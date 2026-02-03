"""Service for creating governance audit log entries."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Mapping

from sqlalchemy.orm import Session

from app.core.request_context import get_request_id
from app.models.audit_log import AuditLogEntry
from app.monitoring.otel import get_current_trace_id
from app.repositories.factory import RepositoryFactory
from app.services.audit_redaction import redact

ActorType = Literal["user", "system", "mcp", "webhook"]
Status = Literal["success", "failed", "denied"]


class AuditService:
    """Create and persist governance audit log entries."""

    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        action: str,
        resource_type: str,
        *,
        actor: Any | None = None,
        actor_type: ActorType = "user",
        actor_id: str | None = None,
        actor_email: str | None = None,
        resource_id: str | None = None,
        description: str | None = None,
        changes: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        status: Status = "success",
        error_message: str | None = None,
        request: Any = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> AuditLogEntry:
        """Create an audit log entry."""
        resolved_actor_id, resolved_actor_email = _resolve_actor_fields(
            actor, actor_id, actor_email
        )
        user_agent = None
        if request is not None:
            user_agent = request.headers.get("user-agent")
            if user_agent:
                user_agent = user_agent[:500]

        metadata_payload = dict(metadata) if metadata else {}
        actor_roles = _extract_actor_roles(actor)
        if actor_roles and "actor_roles" not in metadata_payload:
            metadata_payload["actor_roles"] = actor_roles

        entry = AuditLogEntry(
            timestamp=timestamp or datetime.now(timezone.utc),
            actor_type=actor_type,
            actor_id=resolved_actor_id,
            actor_email=resolved_actor_email,
            actor_ip=_get_client_ip(request),
            actor_user_agent=user_agent,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            changes=_sanitize_changes(changes),
            metadata_json=_sanitize_metadata(metadata_payload),
            status=status,
            error_message=error_message,
            request_id=request_id or get_request_id(),
            trace_id=trace_id or get_current_trace_id(),
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
        )
        RepositoryFactory.create_governance_audit_repository(self.db).write(entry)
        return entry

    def log_changes(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        old_values: Mapping[str, Any] | None,
        new_values: Mapping[str, Any] | None,
        **kwargs: Any,
    ) -> AuditLogEntry | None:
        """Log an update with automatic change detection."""
        changes = _diff_changes(old_values, new_values)
        if not changes:
            return None
        return self.log(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            **kwargs,
        )


def _resolve_actor_fields(
    actor: Any | None,
    actor_id: str | None,
    actor_email: str | None,
) -> tuple[str | None, str | None]:
    resolved_id = actor_id
    resolved_email = actor_email

    if actor is None:
        return resolved_id, resolved_email

    if resolved_id is None:
        if isinstance(actor, Mapping):
            resolved_id = _extract_value(actor, ("id", "actor_id", "user_id"))
        else:
            resolved_id = _first_attr(actor, ("id", "actor_id", "user_id"))

    if resolved_email is None:
        if isinstance(actor, Mapping):
            resolved_email = _extract_value(actor, ("email", "actor_email", "user_email"))
        else:
            resolved_email = _first_attr(actor, ("email", "actor_email", "user_email"))

    return resolved_id, resolved_email


def _extract_actor_roles(actor: Any | None) -> list[str] | None:
    if actor is None:
        return None
    roles: list[str] = []
    if isinstance(actor, Mapping):
        role_value = actor.get("role") or actor.get("actor_role")
        if role_value:
            roles.append(str(role_value))
        role_list = actor.get("roles") or actor.get("role_names")
        if isinstance(role_list, (list, tuple)):
            roles.extend([str(item) for item in role_list if item])
    else:
        role_value = getattr(actor, "role", None) or getattr(actor, "actor_role", None)
        if role_value:
            roles.append(str(role_value))
        role_list = getattr(actor, "roles", None) or getattr(actor, "role_names", None)
        if isinstance(role_list, (list, tuple)):
            for item in role_list:
                if hasattr(item, "name"):
                    name = getattr(item, "name")
                    if name:
                        roles.append(str(name))
                elif item:
                    roles.append(str(item))
    if not roles:
        return None
    # Preserve order but deduplicate
    seen: set[str] = set()
    deduped: list[str] = []
    for role in roles:
        if role not in seen:
            seen.add(role)
            deduped.append(role)
    return deduped


def _sanitize_changes(changes: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not changes:
        return None
    sanitized: dict[str, Any] = {}
    for field, diff in changes.items():
        if isinstance(diff, Mapping):
            old_value = _normalize_value(diff.get("old"))
            new_value = _normalize_value(diff.get("new"))
            redacted_old = _redact_field(field, old_value)
            redacted_new = _redact_field(field, new_value)
            sanitized[field] = {"old": redacted_old, "new": redacted_new}
        else:
            sanitized[field] = _redact_field(field, _normalize_value(diff))
    return sanitized


def _sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    normalized = {key: _normalize_value(value) for key, value in metadata.items()}
    return redact(normalized) or {}


def _diff_changes(
    old_values: Mapping[str, Any] | None,
    new_values: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    old_values = old_values or {}
    new_values = new_values or {}
    changes: dict[str, dict[str, Any]] = {}
    all_keys = set(old_values.keys()) | set(new_values.keys())
    for key in all_keys:
        old_value = _normalize_value(old_values.get(key))
        new_value = _normalize_value(new_values.get(key))
        if old_value != new_value:
            changes[key] = {"old": old_value, "new": new_value}
    return changes


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    return value


def _redact_field(field: str, value: Any) -> Any:
    redacted = redact({field: value}) or {}
    return redacted.get(field)


def _first_attr(obj: Any, names: tuple[str, ...]) -> Any | None:
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return None


def _extract_value(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _get_client_ip(request: Any) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    if hasattr(request, "client") and request.client:
        host = getattr(request.client, "host", None)
        return str(host) if host is not None else None
    return None


def audit_log(db: Session, action: str, resource_type: str, **kwargs: Any) -> AuditLogEntry:
    """Convenience helper."""
    return AuditService(db).log(action, resource_type, **kwargs)
