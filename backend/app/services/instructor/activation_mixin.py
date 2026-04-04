"""Instructor activation and go-live flow for InstructorService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from ...core.exceptions import BusinessRuleException, NotFoundException, ServiceException
from ...models.service_catalog import (
    SERVICE_FORMAT_INSTRUCTOR_LOCATION,
    SERVICE_FORMAT_STUDENT_LOCATION,
)
from ..base import BaseService
from .mixin_base import InstructorMixinBase, get_instructor_service_module


class InstructorActivationMixin(InstructorMixinBase):
    """Instructor go-live activation and prerequisite validation."""

    def _load_go_live_context(self, user_id: str) -> Dict[str, Any]:
        """Load profile, user, and active service format state."""
        profile = self.profile_repository.find_one_by(user_id=user_id)
        if not profile:
            raise NotFoundException("Instructor profile not found")

        user = self.user_repository.get_by_id(user_id)
        active_services = self.service_repository.find_by(
            instructor_profile_id=profile.id,
            is_active=True,
        )
        active_formats: set[str] = set()
        for service in active_services:
            for format_price in getattr(service, "format_prices", []):
                active_formats.add(format_price.format)

        return {
            "profile": profile,
            "user": user,
            "active_formats": active_formats,
        }

    def _validate_go_live_prerequisites(self, context: Dict[str, Any]) -> None:
        """Validate identity, onboarding, and account prerequisites."""
        profile = context["profile"]
        user = context["user"]

        mismatch_sources: list[str] = []
        if profile.identity_name_mismatch:
            mismatch_sources.append("identity verification")
        if profile.bgc_name_mismatch:
            mismatch_sources.append("background check")
        if mismatch_sources:
            mismatch_summary = " and ".join(mismatch_sources)
            raise ServiceException(
                f"Name mismatch detected in {mismatch_summary}. "
                "Please contact support to resolve this before going live.",
                code="name_mismatch_block",
            )

        instructor_service_module = get_instructor_service_module()
        pricing_service = instructor_service_module.PricingService(self.db)
        stripe_service = instructor_service_module.StripeService(
            self.db,
            config_service=self.config_service,
            pricing_service=pricing_service,
        )
        connect_status = (
            stripe_service.check_account_status(profile.id)
            if profile.id
            else {"has_account": False, "onboarding_completed": False}
        )

        missing: list[str] = []
        if not bool(getattr(profile, "skills_configured", False)):
            missing.append("skills")
        if not bool(profile.identity_verified_at):
            missing.append("identity")
        if not bool(connect_status.get("onboarding_completed")):
            missing.append("stripe_connect")
        if (profile.bgc_status or "").lower() != "passed":
            missing.append("background_check")
        if not bool(getattr(user, "phone_verified", False)):
            missing.append("phone_verification")

        if missing:
            message = "Prerequisites not met"
            if "phone_verification" in missing:
                message = "Phone number must be verified before going live"
            raise BusinessRuleException(
                message,
                code="GO_LIVE_PREREQUISITES",
                details={"missing": missing},
            )

    def _validate_go_live_locations(self, context: Dict[str, Any]) -> None:
        """Validate service-area and teaching-location requirements by format."""
        profile = context["profile"]
        active_formats = context["active_formats"]

        if SERVICE_FORMAT_STUDENT_LOCATION in active_formats:
            service_areas = self.service_area_repository.list_for_instructor(
                profile.user_id,
                active_only=True,
            )
            if not service_areas:
                raise BusinessRuleException(
                    "Cannot go live with travel format — add at least one service area first",
                    code="NO_SERVICE_AREAS",
                )

        if SERVICE_FORMAT_INSTRUCTOR_LOCATION in active_formats:
            teaching_locations = self.get_instructor_teaching_locations(profile.user_id)
            if not teaching_locations:
                raise BusinessRuleException(
                    "Cannot go live with 'at my location' format"
                    " — add at least one teaching location first",
                    code="NO_TEACHING_LOCATIONS",
                )

    def _persist_go_live_transition(self, profile: Any) -> Any:
        """Persist the go-live state transition and emit lifecycle events."""
        with self.transaction():
            if not getattr(profile, "onboarding_completed_at", None):
                updated_profile = self.profile_repository.update(
                    profile.id,
                    is_live=True,
                    onboarding_completed_at=datetime.now(timezone.utc),
                    verified_first_name=None,
                    verified_dob=None,
                    bgc_submitted_first_name=None,
                    bgc_submitted_last_name=None,
                    bgc_submitted_dob=None,
                    skills_configured=(
                        True
                        if not getattr(profile, "skills_configured", False)
                        else profile.skills_configured
                    ),
                )
            else:
                updated_profile = self.profile_repository.update(
                    profile.id,
                    is_live=True,
                    verified_first_name=None,
                    verified_dob=None,
                    bgc_submitted_first_name=None,
                    bgc_submitted_last_name=None,
                    bgc_submitted_dob=None,
                )

            instructor_service_module = get_instructor_service_module()
            lifecycle_service = instructor_service_module.InstructorLifecycleService(self.db)
            lifecycle_service.record_went_live(profile.user_id)

        if updated_profile is None:
            raise ServiceException("Failed to update instructor profile", code="update_failed")
        return updated_profile

    @BaseService.measure_operation("instructor.go_live")
    def go_live(self, user_id: str) -> Any:
        """Activate instructor profile if prerequisites are met."""
        context = self._load_go_live_context(user_id)
        self._validate_go_live_prerequisites(context)
        self._validate_go_live_locations(context)
        return self._persist_go_live_transition(context["profile"])
