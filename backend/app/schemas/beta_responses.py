"""Strict response schemas for beta settings endpoints."""

from ._strict_base import StrictModel, StrictRequestModel


class BetaSettingsResponse(StrictModel):
    """Response payload describing beta feature flags."""

    beta_disabled: bool
    beta_phase: str
    allow_signup_without_invite: bool


class BetaSettingsUpdateRequest(StrictRequestModel):
    """Request payload for updating beta settings."""

    beta_disabled: bool
    beta_phase: str
    allow_signup_without_invite: bool


__all__ = [
    "BetaSettingsResponse",
    "BetaSettingsUpdateRequest",
]
