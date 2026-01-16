from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.nl_search import PriceThreshold, RegionSettings
from app.repositories.nl_search_repository import (
    PriceThresholdRepository,
    RegionSettingsRepository,
)


def test_price_threshold_cache_overrides_region(db: Session) -> None:
    repo = PriceThresholdRepository(db)
    unique = uuid.uuid4().hex[:8]
    region_code = f"nyc_{unique}"
    music_category = f"music_{unique}"
    tutoring_category = f"tutoring_{unique}"

    global_threshold = PriceThreshold(
        id=f"pt_global_music_budget_{unique}",
        region_code="global",
        category=music_category,
        intent="budget",
        max_price=30,
        min_price=None,
    )
    global_premium = PriceThreshold(
        id=f"pt_global_tutoring_premium_{unique}",
        region_code="global",
        category=tutoring_category,
        intent="premium",
        max_price=None,
        min_price=80,
    )
    nyc_override = PriceThreshold(
        id=f"pt_nyc_music_budget_{unique}",
        region_code=region_code,
        category=music_category,
        intent="budget",
        max_price=45,
        min_price=None,
    )
    db.add_all([global_threshold, global_premium, nyc_override])
    db.commit()

    all_global = repo.get_all_thresholds(region_code="global")
    assert any(th.id == global_threshold.id for th in all_global)

    cache = repo.build_threshold_cache(region_code=region_code)
    assert cache[(music_category, "budget")]["max_price"] == 45
    assert cache[(tutoring_category, "premium")]["min_price"] == 80


def test_region_settings_queries(db: Session) -> None:
    repo = RegionSettingsRepository(db)
    unique = uuid.uuid4().hex[:8]

    nyc = RegionSettings(
        id=f"region_nyc_{unique}",
        region_code=f"nyc_{unique}",
        region_name="New York City",
        country_code="us",
        timezone="America/New_York",
        price_floor_in_person=30,
        price_floor_remote=20,
        currency_code="USD",
        student_fee_percent=12.5,
        is_active=True,
    )
    sf = RegionSettings(
        id=f"region_sf_{unique}",
        region_code=f"sf_{unique}",
        region_name="San Francisco",
        country_code="us",
        timezone="America/Los_Angeles",
        price_floor_in_person=40,
        price_floor_remote=30,
        currency_code="USD",
        student_fee_percent=12.5,
        is_active=False,
    )
    db.add_all([nyc, sf])
    db.commit()

    fetched = repo.get_by_region_code(nyc.region_code)
    assert fetched is not None
    assert fetched.region_name == "New York City"

    active = repo.get_active_regions()
    assert any(region.region_code == nyc.region_code for region in active)
    assert all(region.is_active for region in active)


def test_get_all_thresholds_without_region(db: Session) -> None:
    repo = PriceThresholdRepository(db)
    unique = uuid.uuid4().hex[:8]

    row_global = PriceThreshold(
        id=f"pt_global_{unique}",
        region_code="global",
        category=f"cat_{unique}",
        intent="budget",
        max_price=25,
        min_price=None,
    )
    row_region = PriceThreshold(
        id=f"pt_region_{unique}",
        region_code=f"region_{unique}",
        category=f"cat_{unique}_2",
        intent="premium",
        max_price=None,
        min_price=100,
    )
    db.add_all([row_global, row_region])
    db.commit()

    all_rows = repo.get_all_thresholds()
    ids = {row.id for row in all_rows}
    assert row_global.id in ids
    assert row_region.id in ids
