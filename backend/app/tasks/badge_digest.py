"""Weekly badge progress digest utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from ..models.user import User
from ..notifications.policy import can_send_now, record_send
from ..repositories.badge_repository import BadgeRepository
from ..services.cache_service import CacheService, CacheServiceSyncAdapter
from ..services.notification_service import NotificationService


def build_weekly_badge_progress_digest(
    user_id: str,
    now_utc: datetime,
    repository: BadgeRepository,
) -> Dict[str, Any]:
    definitions = repository.list_active_badge_definitions()
    awards = repository.list_student_badge_awards(user_id)
    progress_rows = repository.list_student_badge_progress(user_id)

    earned = {row["slug"] for row in awards if row.get("status") == "confirmed"}
    progress_map: Dict[str, Dict[str, Any]] = {
        row["slug"]: row.get("current_progress") or {} for row in progress_rows
    }

    candidates: List[Dict[str, Any]] = []
    for definition in definitions:
        slug = definition.slug
        if slug in earned:
            continue
        progress = progress_map.get(slug)
        if not isinstance(progress, dict):
            continue
        current = progress.get("current")
        goal = progress.get("goal")
        if not isinstance(current, (int, float)) or not isinstance(goal, (int, float)) or goal <= 0:
            continue
        remaining = max(goal - current, 0)
        if remaining <= 0:
            continue
        distance = remaining / goal
        candidates.append(
            {
                "slug": slug,
                "name": definition.name,
                "remaining": remaining,
                "percent": min(100, int((current / goal) * 100)),
                "distance": distance,
            }
        )

    top_items = sorted(candidates, key=lambda item: item["distance"])[:2]
    for item in top_items:
        item.pop("distance", None)

    return {
        "user_id": user_id,
        "generated_at": now_utc,
        "items": top_items,
    }


def send_weekly_digest(
    now_utc: datetime,
    users: Iterable[User],
    repository: BadgeRepository,
    notification_service: Optional[NotificationService],
    cache_service: Optional[CacheService | CacheServiceSyncAdapter],
) -> Dict[str, int]:
    if isinstance(cache_service, CacheService):
        cache_service = CacheServiceSyncAdapter(cache_service)
    summary = {"scanned": 0, "sent": 0}
    for user in users:
        summary["scanned"] += 1
        digest = build_weekly_badge_progress_digest(user.id, now_utc, repository)
        if not digest["items"]:
            continue
        allowed, reason, key = can_send_now(user, now_utc, cache_service)
        if not allowed:
            continue
        if notification_service and notification_service.send_badge_digest_email(
            user, digest["items"]
        ):
            record_send(key, cache_service)
            summary["sent"] += 1
    return summary


__all__ = [
    "build_weekly_badge_progress_digest",
    "send_weekly_digest",
]
