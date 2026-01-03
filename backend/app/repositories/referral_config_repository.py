from typing import Any, Mapping, Optional, cast

from sqlalchemy import text
from sqlalchemy.orm import Session


class ReferralConfigRepository:
    @staticmethod
    def read_latest(db: Session) -> Mapping[str, Any] | None:
        stmt = text(
            """
            SELECT
                enabled,
                student_amount_cents,
                instructor_amount_cents,
                instructor_founding_bonus_cents,
                instructor_standard_bonus_cents,
                min_basket_cents,
                hold_days,
                expiry_months,
                student_global_cap,
                version
            FROM referral_config
            ORDER BY version DESC
            LIMIT 1
            """
        )
        result = db.execute(stmt).mappings().first()
        return cast(Optional[Mapping[str, Any]], result)
