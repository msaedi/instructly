from __future__ import annotations

from pydantic import Field


class ReferralsSettingsMixin:
    referrals_enabled: bool = Field(default=True, description="Enable referral flows")
    referrals_student_amount_cents: int = Field(
        default=2000, description="Reward amount for student-side credits"
    )
    referrals_instructor_amount_cents: int = Field(
        default=5000, description="Reward amount for instructor-side credits"
    )
    referrals_min_basket_cents: int = Field(
        default=7500, description="Minimum order amount to apply referral credit"
    )
    referrals_hold_days: int = Field(default=7, description="Days to hold rewards before unlock")
    referrals_expiry_months: int = Field(
        default=6, description="Months before unlocked rewards expire"
    )
    referrals_student_global_cap: int = Field(
        default=200, description="Maximum active student rewards per referrer"
    )
