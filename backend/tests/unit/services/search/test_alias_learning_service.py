from __future__ import annotations

from ulid import ULID

from app.models.location_alias import LocationAlias
from app.models.region_boundary import RegionBoundary
from app.models.unresolved_location_query import UnresolvedLocationQuery
from app.repositories.unresolved_location_query_repository import UnresolvedLocationQueryRepository
from app.services.search.alias_learning_service import AliasLearningService


def _create_region(
    db,
    *,
    region_type: str,
    region_name: str,
    parent_region: str | None = None,
) -> RegionBoundary:
    boundary = RegionBoundary(
        region_type=region_type,
        region_code=str(ULID()),
        region_name=region_name,
        parent_region=parent_region,
        region_metadata={"test": True},
    )
    db.add(boundary)
    db.flush()
    return boundary


class TestAliasLearningService:
    def test_learns_from_consistent_clicks(self, db):
        region_type = "test"
        region = _create_region(
            db,
            region_type=region_type,
            region_name="Upper East Side-Carnegie Hill",
            parent_region="Manhattan",
        )

        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized="museum mile",
            sample_original_queries=["museum mile"],
            search_count=5,
            unique_user_count=5,
            status="pending",
        )
        db.add(unresolved)
        db.flush()

        repo = UnresolvedLocationQueryRepository(db)
        for _ in range(5):
            repo.record_click("museum mile", region_boundary_id=str(region.id), original_query="museum mile")

        service = AliasLearningService(db, region_code=region_type)
        learned = service.maybe_learn_from_query("museum mile")

        assert learned is not None
        assert learned.alias_normalized == "museum mile"
        assert learned.region_boundary_id == str(region.id)
        assert learned.confidence >= 0.9

        alias = (
            db.query(LocationAlias)
            .filter(LocationAlias.alias_normalized == "museum mile")
            .first()
        )
        assert isinstance(alias, LocationAlias)
        assert alias.region_boundary_id == str(region.id)
        assert alias.source == "user_learning"

        refreshed = (
            db.query(UnresolvedLocationQuery)
            .filter(UnresolvedLocationQuery.query_normalized == "museum mile")
            .first()
        )
        assert isinstance(refreshed, UnresolvedLocationQuery)
        assert refreshed.status == "learned"
        assert str(refreshed.resolved_region_boundary_id) == str(region.id)

    def test_does_not_learn_when_confidence_too_low(self, db):
        region_type = "test"
        r1 = _create_region(db, region_type=region_type, region_name="Upper East Side", parent_region="Manhattan")
        r2 = _create_region(db, region_type=region_type, region_name="Upper West Side", parent_region="Manhattan")

        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized="central park-ish",
            sample_original_queries=["central park-ish"],
            search_count=10,
            unique_user_count=10,
            status="pending",
        )
        db.add(unresolved)
        db.flush()

        repo = UnresolvedLocationQueryRepository(db)
        for _ in range(2):
            repo.record_click("central park-ish", region_boundary_id=str(r1.id), original_query="central park-ish")
        for _ in range(2):
            repo.record_click("central park-ish", region_boundary_id=str(r2.id), original_query="central park-ish")

        service = AliasLearningService(db, region_code=region_type)
        learned = service.maybe_learn_from_query("central park-ish")

        assert learned is None
        alias = (
            db.query(LocationAlias)
            .filter(LocationAlias.alias_normalized == "central park-ish")
            .first()
        )
        assert alias is None

    def test_existing_alias_is_not_overridden(self, db):
        region_type = "test"
        region = _create_region(db, region_type=region_type, region_name="Tribeca", parent_region="Manhattan")

        db.add(
            LocationAlias(
                alias_normalized="museum mile",
                region_boundary_id=str(region.id),
                status="active",
                confidence=1.0,
                user_count=1,
                source="manual",
            )
        )
        db.flush()

        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized="museum mile",
            sample_original_queries=["museum mile"],
            search_count=10,
            unique_user_count=10,
            status="pending",
        )
        db.add(unresolved)
        db.flush()

        repo = UnresolvedLocationQueryRepository(db)
        for _ in range(5):
            repo.record_click("museum mile", region_boundary_id=str(region.id), original_query="museum mile")

        service = AliasLearningService(db, region_code=region_type)
        learned = service.maybe_learn_from_query("museum mile")

        assert learned is None
        refreshed = (
            db.query(UnresolvedLocationQuery)
            .filter(UnresolvedLocationQuery.query_normalized == "museum mile")
            .first()
        )
        assert isinstance(refreshed, UnresolvedLocationQuery)
        assert refreshed.status in {"pending", "manual_review"}
