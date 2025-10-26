from scripts.seed_data import BADGE_SEED_DEFINITIONS, seed_badge_definitions
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models.badge import BadgeDefinition


def _create_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_seed_badges_populates_descriptions():
    engine = _create_engine()

    # First seed should insert all badges with descriptions
    seed_badge_definitions(engine, verbose=False)
    with Session(engine) as session:
        rows = session.execute(
            select(BadgeDefinition.slug, BadgeDefinition.description)
        ).all()
        assert len(rows) == len(BADGE_SEED_DEFINITIONS)
        assert all(description for _slug, description in rows)

    # Second seed remains idempotent and keeps descriptions intact
    seed_badge_definitions(engine, verbose=False)
    with Session(engine) as session:
        all_badges = session.query(BadgeDefinition).all()
        assert len(all_badges) == len(BADGE_SEED_DEFINITIONS)
        assert all(badge.description for badge in all_badges)
