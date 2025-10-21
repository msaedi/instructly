from __future__ import annotations

import pytest
from sqlalchemy import text

from ..conftest import test_engine


@pytest.fixture(scope="session", autouse=True)
def ensure_referral_codes_user_active_index() -> None:
    with test_engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_codes_user_active
                ON referral_codes(referrer_user_id) WHERE status='active'
                """
            )
        )
        conn.commit()
