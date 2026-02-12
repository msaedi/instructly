from typing import Any, Mapping, Optional, cast

from sqlalchemy.orm import Session

from app.models.referrals import ReferralConfig


class ReferralConfigRepository:
    @staticmethod
    def read_latest(db: Session) -> Mapping[str, Any] | None:
        row = db.query(ReferralConfig).order_by(ReferralConfig.version.desc()).limit(1).first()
        if row is None:
            return None

        result: Mapping[str, Any] = {
            "enabled": row.enabled,
            "student_amount_cents": row.student_amount_cents,
            "instructor_amount_cents": row.instructor_amount_cents,
            "instructor_founding_bonus_cents": row.instructor_founding_bonus_cents,
            "instructor_standard_bonus_cents": row.instructor_standard_bonus_cents,
            "min_basket_cents": row.min_basket_cents,
            "hold_days": row.hold_days,
            "expiry_months": row.expiry_months,
            "student_global_cap": row.student_global_cap,
            "version": row.version,
        }
        return cast(Optional[Mapping[str, Any]], result)
