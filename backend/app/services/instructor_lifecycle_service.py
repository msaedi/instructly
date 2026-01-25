# backend/app/services/instructor_lifecycle_service.py
"""
Instructor lifecycle event tracking for funnel analytics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..repositories.instructor_lifecycle_repository import InstructorLifecycleRepository
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from .base import BaseService
from .config_service import ConfigService

FUNNEL_STAGES: list[str] = [
    "registered",
    "profile_submitted",
    "services_configured",
    "bgc_initiated",
    "bgc_completed",
    "identity_verified",
    "went_live",
]

STAGE_DESCRIPTIONS: dict[str, str] = {
    "registered": "User completed registration as instructor",
    "profile_submitted": "Profile info saved",
    "services_configured": "At least one service added",
    "bgc_initiated": "Background check started",
    "bgc_completed": "Background check finished",
    "identity_verified": "Identity verification completed",
    "went_live": "Instructor activated and can receive bookings",
    "paused": "Instructor paused their account",
    "reactivated": "Instructor reactivated after pause",
}


class InstructorLifecycleService(BaseService):
    """
    Tracks instructor lifecycle events for funnel analytics.

    Called from:
    - AuthService (registration)
    - InstructorService (profile updates)
    - BackgroundCheckService (BGC status changes)
    """

    def __init__(self, db: Session):
        super().__init__(db)
        self.repository = InstructorLifecycleRepository(db)

    def _should_record_stage(self, user_id: str, event_type: str) -> bool:
        if event_type not in FUNNEL_STAGES:
            return True
        current_stage = self.repository.get_current_stage(user_id)
        if not current_stage:
            return True
        if current_stage not in FUNNEL_STAGES:
            return True
        return FUNNEL_STAGES.index(event_type) > FUNNEL_STAGES.index(current_stage)

    @BaseService.measure_operation("instructor_lifecycle.record_registration")
    def record_registration(self, user_id: str, is_founding: bool = False) -> None:
        """Record that an instructor registered."""
        if not self._should_record_stage(user_id, "registered"):
            return
        self.repository.record_event(
            user_id=user_id,
            event_type="registered",
            metadata={"is_founding": is_founding},
        )

    @BaseService.measure_operation("instructor_lifecycle.record_profile_submitted")
    def record_profile_submitted(self, user_id: str) -> None:
        """Record that profile was completed."""
        if not self._should_record_stage(user_id, "profile_submitted"):
            return
        self.repository.record_event(user_id=user_id, event_type="profile_submitted")

    @BaseService.measure_operation("instructor_lifecycle.record_services_configured")
    def record_services_configured(self, user_id: str) -> None:
        """Record that services were configured."""
        if not self._should_record_stage(user_id, "services_configured"):
            return
        self.repository.record_event(user_id=user_id, event_type="services_configured")

    @BaseService.measure_operation("instructor_lifecycle.record_bgc_initiated")
    def record_bgc_initiated(self, user_id: str) -> None:
        """Record that BGC was started."""
        if not self._should_record_stage(user_id, "bgc_initiated"):
            return
        self.repository.record_event(user_id=user_id, event_type="bgc_initiated")

    @BaseService.measure_operation("instructor_lifecycle.record_bgc_completed")
    def record_bgc_completed(self, user_id: str, status: str) -> None:
        """Record BGC completion with pass/fail in metadata."""
        if not self._should_record_stage(user_id, "bgc_completed"):
            return
        self.repository.record_event(
            user_id=user_id,
            event_type="bgc_completed",
            metadata={"status": status},
        )

    @BaseService.measure_operation("instructor_lifecycle.record_went_live")
    def record_went_live(self, user_id: str) -> None:
        """Record that instructor went live."""
        if not self._should_record_stage(user_id, "went_live"):
            return
        self.repository.record_event(user_id=user_id, event_type="went_live")

    @BaseService.measure_operation("instructor_lifecycle.record_paused")
    def record_paused(self, user_id: str, reason: str | None = None) -> None:
        """Record that instructor paused."""
        latest = self.repository.get_latest_event_for_user(user_id)
        if latest and latest.event_type == "paused":
            return
        metadata = {"reason": reason} if reason else None
        self.repository.record_event(user_id=user_id, event_type="paused", metadata=metadata)

    @BaseService.measure_operation("instructor_lifecycle.record_reactivated")
    def record_reactivated(self, user_id: str) -> None:
        """Record that instructor reactivated."""
        latest = self.repository.get_latest_event_for_user(user_id)
        if latest and latest.event_type == "reactivated":
            return
        self.repository.record_event(user_id=user_id, event_type="reactivated")

    @BaseService.measure_operation("instructor_lifecycle.get_funnel_summary")
    def get_funnel_summary(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get funnel summary with stage counts and conversion rates.
        Also includes founding cap usage.
        """
        counts = self.repository.count_by_stage(start_date=start_date, end_date=end_date)

        stages = [
            {
                "stage": stage,
                "count": counts.get(stage, 0),
                "description": STAGE_DESCRIPTIONS.get(stage, stage),
            }
            for stage in FUNNEL_STAGES
        ]

        conversion_rates: List[Dict[str, Any]] = []
        for idx in range(len(FUNNEL_STAGES) - 1):
            from_stage = FUNNEL_STAGES[idx]
            to_stage = FUNNEL_STAGES[idx + 1]
            from_count = counts.get(from_stage, 0)
            to_count = counts.get(to_stage, 0)
            rate = round((to_count / from_count), 4) if from_count else 0.0
            conversion_rates.append({"from_stage": from_stage, "to_stage": to_stage, "rate": rate})

        config_service = ConfigService(self.db)
        pricing_config, _updated_at = config_service.get_pricing_config()
        cap_raw = pricing_config.get("founding_instructor_cap", 100)
        try:
            cap = int(cap_raw)
        except (TypeError, ValueError):
            cap = 100

        profile_repo = InstructorProfileRepository(self.db)
        used = profile_repo.count_founding_instructors()
        remaining = max(0, cap - used)

        return {
            "stages": stages,
            "conversion_rates": conversion_rates,
            "founding_cap": {
                "cap": cap,
                "used": used,
                "remaining": remaining,
                "is_founding_phase": used < cap,
            },
            "time_window": {
                "start": start_date,
                "end": end_date,
            },
        }

    @BaseService.measure_operation("instructor_lifecycle.get_stuck_instructors")
    def get_stuck_instructors(
        self,
        stuck_days: int = 7,
        stage: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get stuck instructors with summary by stage."""
        stuck = self.repository.get_stuck_instructors(
            stuck_days=stuck_days,
            stage=stage,
            limit=limit,
        )

        summary_counts: dict[str, int] = {}
        for row in stuck:
            stage_value = row.get("stage")
            if not stage_value:
                continue
            summary_counts[stage_value] = summary_counts.get(stage_value, 0) + 1

        summary = [
            {"stage": stage_key, "stuck_count": count}
            for stage_key, count in summary_counts.items()
        ]

        return {
            "summary": summary,
            "instructors": stuck,
            "total_stuck": len(stuck),
        }
