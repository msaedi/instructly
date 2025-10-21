from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.referrals_config_service import get_effective_config, invalidate_cache


@pytest.fixture(autouse=True)
def _clear_referral_config(db):
    invalidate_cache()
    db.execute(text("DELETE FROM referral_config"))
    db.commit()
    yield
    invalidate_cache()
    db.execute(text("DELETE FROM referral_config"))
    db.commit()


def _insert_config(
    db,
    *,
    version: int,
    enabled: bool = True,
    student_amount_cents: int = 2000,
    instructor_amount_cents: int = 5000,
    min_basket_cents: int = 8000,
    hold_days: int = 7,
    expiry_months: int = 6,
    student_global_cap: int = 20,
    updated_by: str = "test",
    note: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO referral_config (
                id,
                version,
                enabled,
                student_amount_cents,
                instructor_amount_cents,
                min_basket_cents,
                hold_days,
                expiry_months,
                student_global_cap,
                updated_by,
                note
            ) VALUES (
                :id,
                :version,
                :enabled,
                :student_amount_cents,
                :instructor_amount_cents,
                :min_basket_cents,
                :hold_days,
                :expiry_months,
                :student_global_cap,
                :updated_by,
                :note
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "version": version,
            "enabled": enabled,
            "student_amount_cents": student_amount_cents,
            "instructor_amount_cents": instructor_amount_cents,
            "min_basket_cents": min_basket_cents,
            "hold_days": hold_days,
            "expiry_months": expiry_months,
            "student_global_cap": student_global_cap,
            "updated_by": updated_by,
            "note": note,
        },
    )
    db.commit()


def test_returns_defaults_when_table_empty(db):
    config = get_effective_config(db)

    assert config["source"] == "defaults"
    assert config["version"] is None
    assert config["enabled"] is True
    assert config["student_amount_cents"] == 2000
    assert config["instructor_amount_cents"] == 5000
    assert config["min_basket_cents"] == 8000
    assert config["hold_days"] == 7
    assert config["expiry_months"] == 6
    assert config["student_global_cap"] == 20


def test_returns_database_row_when_present(db):
    _insert_config(
        db,
        version=1,
        enabled=False,
        student_amount_cents=2500,
        instructor_amount_cents=6000,
        min_basket_cents=9000,
        hold_days=5,
        expiry_months=12,
        student_global_cap=80,
        updated_by="tester",
        note="seeded",
    )

    config = get_effective_config(db)

    assert config["source"] == "db"
    assert config["version"] == 1
    assert config["enabled"] is False
    assert config["student_amount_cents"] == 2500
    assert config["instructor_amount_cents"] == 6000
    assert config["min_basket_cents"] == 9000
    assert config["hold_days"] == 5
    assert config["expiry_months"] == 12
    assert config["student_global_cap"] == 80


def test_cache_and_invalidate_flow(db):
    _insert_config(db, version=1, student_amount_cents=2100, student_global_cap=30)
    invalidate_cache()

    first = get_effective_config(db)
    assert first["version"] == 1
    assert first["student_amount_cents"] == 2100
    assert first["student_global_cap"] == 30

    _insert_config(db, version=2, student_amount_cents=2400, student_global_cap=100)

    second = get_effective_config(db)
    assert second["version"] == 1
    assert second["student_amount_cents"] == 2100

    invalidate_cache()

    third = get_effective_config(db)
    assert third["version"] == 2
    assert third["student_amount_cents"] == 2400
    assert third["student_global_cap"] == 100
