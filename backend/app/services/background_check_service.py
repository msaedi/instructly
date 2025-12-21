"""Service for initiating Checkr background checks via hosted invitations."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, TypedDict, cast
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.exceptions import NotFoundException, ServiceException
from ..integrations.checkr_client import CheckrClient, CheckrError
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.bgc import BackgroundCheckStatusLiteral
from .base import BaseService


class InviteResult(TypedDict, total=False):
    status: BackgroundCheckStatusLiteral
    report_id: Optional[str]
    candidate_id: Optional[str]
    invitation_id: Optional[str]


US_STATE_ABBREVIATIONS = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "PUERTO RICO": "PR",
}


class BackgroundCheckService(BaseService):
    """Coordinates Checkr interactions and instructor profile updates."""

    logger = logging.getLogger(__name__)

    def __init__(
        self,
        db: Session,
        *,
        client: CheckrClient,
        repository: InstructorProfileRepository,
        package: str,
        env: str,
        is_fake_client: bool = False,
        config_error: str | None = None,
    ) -> None:
        super().__init__(db)
        self.client = client
        self.repository = repository
        self.package = package
        self.env = env
        self.is_fake_client = is_fake_client
        self.config_error = config_error

    @BaseService.measure_operation("bgc.invite")
    def invite(self, instructor_id: str, *, package_override: str | None = None) -> InviteResult:
        """Create a Checkr candidate and hosted invitation for an instructor."""

        profile = self.repository.get_by_id(instructor_id, load_relationships=True)
        if not profile:
            raise NotFoundException(
                message="Instructor profile not found",
                code="INSTRUCTOR_NOT_FOUND",
                details={"instructor_id": instructor_id},
            )

        user = profile.user
        if not user:
            raise ServiceException("Instructor profile missing associated user")

        zip_code_value = getattr(user, "zip_code", None)
        if not zip_code_value:
            raise ServiceException(
                "Primary teaching ZIP code missing",
                code="invalid_work_location",
                details={"instructor_id": instructor_id},
            )
        normalized_zip = self._normalize_zip(zip_code_value)
        work_location = self._resolve_work_location(normalized_zip)

        candidate_payload: Dict[str, Any] = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        }

        optional_fields: Dict[str, Optional[str]] = {
            "phone": getattr(user, "phone", None),
            "zipcode": normalized_zip,
        }

        # Safely include optional fields supported by hosted invitations
        candidate_payload.update({key: value for key, value in optional_fields.items() if value})
        candidate_payload["work_location"] = work_location

        # Package slug comes from the request override or defaults to settings.checkr_package,
        # which maps to CHECKR_DEFAULT_PACKAGE / CHECKR_PACKAGE env vars.
        resolved_package = (package_override or self.package or "").strip()
        if not resolved_package:
            raise ServiceException("Checkr package slug is required")

        redirect_url = f"{settings.frontend_url.rstrip('/')}/instructor/onboarding/status"

        site_mode = str(getattr(settings, "site_mode", "") or "local").strip() or "local"
        idempotency_key = f"candidate-{site_mode}-{profile.id}"
        # Deterministic key avoids duplicate candidates if we retry within 24 hours.

        try:
            candidate = self.client.create_candidate(
                idempotency_key=idempotency_key,
                **candidate_payload,
            )
            candidate_id = candidate.get("id")
            if not candidate_id:
                raise ServiceException("Checkr candidate response missing identifier")

            invite_kwargs: Dict[str, Any] = {
                "candidate_id": candidate_id,
                "package": resolved_package,
                "redirect_url": redirect_url,
                "candidate": candidate_payload,
                "work_locations": [work_location],
            }
            workflow_value = getattr(settings, "checkr_hosted_workflow", None)
            if workflow_value:
                invite_kwargs["workflow"] = workflow_value

            self.logger.debug(
                "Checkr invite payload",
                extra={
                    "evt": "bgc_invite_payload",
                    "candidate_id": candidate_id,
                    "package": resolved_package,
                    "workflow": workflow_value,
                },
            )
            invitation = self.client.create_invitation(**invite_kwargs)
        except CheckrError as exc:
            details = {"status_code": exc.status_code} if exc.status_code else {}
            raise ServiceException(
                "Failed to initiate instructor background check", details=details
            ) from exc

        report_id = cast(Optional[str], invitation.get("report_id"))
        invitation_id = cast(Optional[str], invitation.get("id"))

        with self.transaction():
            self.repository.update_bgc(
                instructor_id,
                status="pending",
                report_id=report_id,
                env=self.env,
                report_result=None,
                candidate_id=candidate_id,
                invitation_id=invitation_id,
                note=None,
                includes_canceled=False,
            )

        return {
            "status": "pending",
            "report_id": report_id,
            "candidate_id": candidate_id,
            "invitation_id": invitation_id,
        }

    @BaseService.measure_operation("bgc.webhook_update")
    def update_status_from_report(
        self,
        report_id: str,
        *,
        status: BackgroundCheckStatusLiteral,
        completed: bool,
        result: str | None = None,
    ) -> bool:
        """Update instructor profile fields based on a Checkr report event."""

        completed_at = datetime.now(timezone.utc) if completed else None

        with self.transaction():
            updated: int = self.repository.update_bgc_by_report_id(
                report_id,
                status=status,
                completed_at=completed_at,
                result=result,
            )

        if not updated:
            self.logger.info(
                "No instructor profile updated for Checkr report", extra={"report_id": report_id}
            )

        return updated > 0

    @staticmethod
    def _normalize_zip(zip_code: str) -> str:
        cleaned = (zip_code or "").strip().replace("-", "")
        if len(cleaned) >= 5 and cleaned[:5].isdigit():
            return cleaned[:5]
        raise ServiceException(
            "Invalid ZIP code format",
            code="invalid_work_location",
            details={"zip_code": zip_code, "reason": "invalid_format"},
        )

    def _resolve_work_location(self, zip_code: str) -> dict[str, str]:
        provider_name = "mapbox"
        token = getattr(settings, "mapbox_access_token", None)
        if not token:
            raise ServiceException(
                "Unable to resolve work location",
                code="invalid_work_location",
                details={
                    "zip_code": zip_code,
                    "reason": "missing_mapbox_token",
                    "provider": provider_name,
                },
            )

        encoded_zip = quote(zip_code, safe="")
        try:
            resp = httpx.get(
                f"https://api.mapbox.com/geocoding/v5/mapbox.places/{encoded_zip}.json",
                params={"access_token": token, "types": "address,place,postcode"},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise ServiceException(
                "Geocoding provider unavailable",
                code="geocoding_provider_error",
                details={
                    "zip_code": zip_code,
                    "provider": provider_name,
                    "provider_status": getattr(getattr(exc, "response", None), "status_code", None),
                    "error_message": str(exc),
                },
            ) from exc

        features = data.get("features") if isinstance(data, dict) else None
        if not features:
            raise ServiceException(
                "Unable to resolve work location",
                code="invalid_work_location",
                details={
                    "zip_code": zip_code,
                    "reason": "zero_results",
                    "provider": provider_name,
                },
            )

        feature = features[0] or {}
        context = feature.get("context") or []

        def _find(prefix: str) -> dict[str, Any] | None:
            for entry in context:
                if isinstance(entry, dict) and str(entry.get("id", "")).startswith(prefix):
                    return entry
            return None

        city_value = (feature.get("text", "") or "").strip()
        place_entry = _find("place")
        if place_entry:
            city_value = (place_entry.get("text", "") or city_value).strip()

        region_entry = _find("region")
        country_entry = _find("country")
        state_value = self._normalize_state((region_entry or {}).get("text"))
        country_value = (
            ((country_entry or {}).get("short_code") or (country_entry or {}).get("text") or "US")
            .strip()
            .upper()
        )  # Checkr expects uppercase country codes (e.g., "US" not "us")
        if len(country_value) > 3:
            country_value = "US"

        if not state_value or not city_value:
            raise ServiceException(
                "Unable to resolve work location",
                code="invalid_work_location",
                details={
                    "zip_code": zip_code,
                    "reason": "missing_location_components",
                    "provider": provider_name,
                },
            )

        return {
            "country": country_value or "US",
            "state": state_value,
            "city": city_value,
        }

    @staticmethod
    def _normalize_state(raw_state: Optional[str]) -> str:
        if not raw_state:
            return ""
        cleaned = raw_state.strip()
        if not cleaned:
            return ""
        if len(cleaned) == 2 and cleaned.isalpha():
            return cleaned.upper()
        upper = cleaned.upper()
        return US_STATE_ABBREVIATIONS.get(upper, upper[:2])
