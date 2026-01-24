# backend/app/services/mcp_instructor_service.py
"""Service layer for MCP instructor operations."""

from __future__ import annotations

import base64
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.instructor import InstructorProfile
from app.repositories.mcp_instructor_repository import MCPInstructorRepository
from app.services.base import BaseService


def derive_instructor_status(profile: InstructorProfile) -> str:
    """Return instructor status from onboarding flags."""
    if getattr(profile, "is_live", False):
        return "live"
    if getattr(profile, "onboarding_completed_at", None):
        return "paused"
    if getattr(profile, "skills_configured", False) or getattr(profile, "bgc_status", None):
        return "onboarding"
    return "registered"


def _encode_cursor(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


def _decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.urlsafe_b64decode((cursor + padding).encode("utf-8")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - input validation
        raise ValueError("Invalid cursor") from exc
    return decoded


class MCPInstructorService(BaseService):
    """Business logic for MCP instructor admin endpoints."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.repository = MCPInstructorRepository(db)

    @BaseService.measure_operation("mcp_instructors.list")
    def list_instructors(
        self,
        *,
        status: str | None,
        is_founding: bool | None,
        service_slug: str | None,
        category_slug: str | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        decoded_cursor = _decode_cursor(cursor)

        profiles, next_cursor_raw = self.repository.list_instructors(
            status=status,
            is_founding=is_founding,
            service_slug=service_slug,
            category_slug=category_slug,
            limit=limit,
            cursor=decoded_cursor,
        )

        profile_ids = [profile.id for profile in profiles]
        user_ids = [profile.user_id for profile in profiles]

        services_map = self.repository.get_service_lists_for_profiles(profile_ids)
        booking_counts = self.repository.get_booking_completed_counts(user_ids)
        review_stats = self.repository.get_review_stats(user_ids)

        items: list[dict[str, Any]] = []
        for profile in profiles:
            user = profile.user
            first = (getattr(user, "first_name", "") or "").strip()
            last = (getattr(user, "last_name", "") or "").strip()
            name = " ".join(part for part in [first, last] if part).strip()
            services_info = services_map.get(profile.user_id, {"services": [], "categories": []})
            rating_info = review_stats.get(profile.user_id, {"rating_avg": 0.0})

            items.append(
                {
                    "user_id": profile.user_id,
                    "name": name,
                    "email": getattr(user, "email", ""),
                    "status": derive_instructor_status(profile),
                    "is_founding": bool(getattr(profile, "is_founding_instructor", False)),
                    "founding_granted_at": getattr(profile, "founding_granted_at", None),
                    "services": services_info["services"],
                    "categories": services_info["categories"],
                    "live_at": getattr(profile, "onboarding_completed_at", None)
                    if getattr(profile, "is_live", False)
                    else None,
                    "rating_avg": float(rating_info.get("rating_avg", 0.0)),
                    "bookings_completed": int(booking_counts.get(profile.user_id, 0)),
                    "admin_url": f"/admin/instructors/{profile.id}",
                }
            )

        next_cursor = _encode_cursor(next_cursor_raw) if next_cursor_raw else None

        return {
            "items": items,
            "next_cursor": next_cursor,
            "limit": limit,
        }

    @BaseService.measure_operation("mcp_instructors.coverage")
    def get_service_coverage(self, *, status: str, group_by: str, top: int) -> dict[str, Any]:
        coverage = self.repository.get_service_coverage(
            status=status,
            group_by=group_by,
            top=top,
        )

        return {
            "group_by": group_by,
            "labels": coverage.get("labels", []),
            "values": coverage.get("values", []),
            "total_instructors": coverage.get("total_instructors", 0),
            "total_services_offered": coverage.get("total_services_offered", 0),
        }

    @BaseService.measure_operation("mcp_instructors.detail")
    def get_instructor_detail(self, identifier: str) -> dict[str, Any]:
        profile = self.repository.get_instructor_by_identifier(identifier)
        if not profile:
            raise NotFoundException("Instructor not found")

        user = profile.user
        first = (getattr(user, "first_name", "") or "").strip()
        last = (getattr(user, "last_name", "") or "").strip()
        name = " ".join(part for part in [first, last] if part).strip()

        booking_stats = self.repository.get_booking_stats(profile.user_id)
        review_stats = self.repository.get_review_stats_for_user(profile.user_id)
        response_rate = getattr(profile, "response_rate", None)
        response_rate_value = float(response_rate) if response_rate is not None else None

        services = []
        for service in profile.instructor_services:
            if not getattr(service, "is_active", False):
                continue
            catalog = service.catalog_entry
            category = catalog.category if catalog else None
            services.append(
                {
                    "name": getattr(catalog, "name", ""),
                    "slug": getattr(catalog, "slug", ""),
                    "category": getattr(category, "name", "") if category else "",
                    "hourly_rate": service.hourly_rate,
                    "is_active": bool(getattr(service, "is_active", False)),
                }
            )

        return {
            "user_id": profile.user_id,
            "name": name,
            "email": getattr(user, "email", ""),
            "phone": getattr(user, "phone", None),
            "status": derive_instructor_status(profile),
            "is_founding": bool(getattr(profile, "is_founding_instructor", False)),
            "founding_granted_at": getattr(profile, "founding_granted_at", None),
            "admin_url": f"/admin/instructors/{profile.id}",
            "live_at": getattr(profile, "onboarding_completed_at", None)
            if getattr(profile, "is_live", False)
            else None,
            "onboarding": {
                "profile_created_at": getattr(profile, "created_at", None),
                "profile_updated_at": getattr(profile, "updated_at", None),
                "identity_verified_at": getattr(profile, "identity_verified_at", None),
                "background_check_uploaded_at": getattr(
                    profile, "background_check_uploaded_at", None
                ),
                "bgc_invited_at": getattr(profile, "bgc_invited_at", None),
                "bgc_completed_at": getattr(profile, "bgc_completed_at", None),
                "onboarding_completed_at": getattr(profile, "onboarding_completed_at", None),
            },
            "bgc": {
                "status": getattr(profile, "bgc_status", None),
                "completed_at": getattr(profile, "bgc_completed_at", None),
                "valid_until": getattr(profile, "bgc_valid_until", None),
            },
            "services": services,
            "stats": {
                "bookings_completed": booking_stats.get("completed", 0),
                "bookings_cancelled": booking_stats.get("cancelled", 0),
                "no_shows": booking_stats.get("no_show", 0),
                "rating_avg": review_stats.get("rating_avg", 0.0),
                "rating_count": review_stats.get("rating_count", 0),
                "response_rate": response_rate_value,
            },
        }
