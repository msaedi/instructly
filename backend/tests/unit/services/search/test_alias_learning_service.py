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
    def test_blank_query_returns_none(self, db):
        service = AliasLearningService(db)

        assert service.maybe_learn_from_query("   ") is None

    def test_missing_query_returns_none(self, db):
        service = AliasLearningService(db)
        query = f"missing {ULID()}".lower()

        assert service.maybe_learn_from_query(query) is None

    def test_learns_from_consistent_clicks(self, db):
        region_type = "test"
        region = _create_region(
            db,
            region_type=region_type,
            region_name="Upper East Side-Carnegie Hill",
            parent_region="Manhattan",
        )
        query = f"museum mile {ULID()}".lower()

        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=query,
            sample_original_queries=[query],
            search_count=5,
            unique_user_count=5,
            status="pending",
        )
        db.add(unresolved)
        db.flush()

        repo = UnresolvedLocationQueryRepository(db)
        for _ in range(5):
            repo.record_click(query, region_boundary_id=str(region.id), original_query=query)

        service = AliasLearningService(db, region_code=region_type)
        learned = service.maybe_learn_from_query(query)

        assert learned is not None
        assert learned.alias_normalized == query
        assert learned.region_boundary_id == str(region.id)
        assert learned.confidence >= 0.9

        alias = (
            db.query(LocationAlias)
            .filter(LocationAlias.alias_normalized == query)
            .first()
        )
        assert isinstance(alias, LocationAlias)
        assert alias.region_boundary_id == str(region.id)
        assert alias.source == "user_learning"

        refreshed = (
            db.query(UnresolvedLocationQuery)
            .filter(UnresolvedLocationQuery.query_normalized == query)
            .first()
        )
        assert isinstance(refreshed, UnresolvedLocationQuery)
        assert refreshed.status == "learned"
        assert str(refreshed.resolved_region_boundary_id) == str(region.id)

    def test_does_not_learn_when_confidence_too_low(self, db):
        region_type = "test"
        r1 = _create_region(db, region_type=region_type, region_name="Upper East Side", parent_region="Manhattan")
        r2 = _create_region(db, region_type=region_type, region_name="Upper West Side", parent_region="Manhattan")
        query = f"central park-ish {ULID()}".lower()

        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=query,
            sample_original_queries=[query],
            search_count=10,
            unique_user_count=10,
            status="pending",
        )
        db.add(unresolved)
        db.flush()

        repo = UnresolvedLocationQueryRepository(db)
        for _ in range(2):
            repo.record_click(query, region_boundary_id=str(r1.id), original_query=query)
        for _ in range(2):
            repo.record_click(query, region_boundary_id=str(r2.id), original_query=query)

        service = AliasLearningService(db, region_code=region_type)
        learned = service.maybe_learn_from_query(query)

        assert learned is None
        alias = (
            db.query(LocationAlias)
            .filter(LocationAlias.alias_normalized == query)
            .first()
        )
        assert alias is None

    def test_existing_alias_is_not_overridden(self, db):
        region_type = "test"
        region = _create_region(db, region_type=region_type, region_name="Tribeca", parent_region="Manhattan")
        query = f"museum mile {ULID()}".lower()

        db.add(
            LocationAlias(
                alias_normalized=query,
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
            query_normalized=query,
            sample_original_queries=[query],
            search_count=10,
            unique_user_count=10,
            status="pending",
        )
        db.add(unresolved)
        db.flush()

        repo = UnresolvedLocationQueryRepository(db)
        for _ in range(5):
            repo.record_click(query, region_boundary_id=str(region.id), original_query=query)

        service = AliasLearningService(db, region_code=region_type)
        learned = service.maybe_learn_from_query(query)

        assert learned is None
        refreshed = (
            db.query(UnresolvedLocationQuery)
            .filter(UnresolvedLocationQuery.query_normalized == query)
            .first()
        )
        assert isinstance(refreshed, UnresolvedLocationQuery)
        assert refreshed.status in {"pending", "manual_review"}

    def test_process_pending_learns_rows(self, db):
        region_type = f"test-{ULID()}".lower()
        region = _create_region(
            db,
            region_type=region_type,
            region_name="Chelsea",
            parent_region="Manhattan",
        )
        query = f"pending {ULID()}".lower()
        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=query,
            sample_original_queries=[query],
            search_count=5,
            unique_user_count=5,
            status="pending",
            click_region_counts={},
            click_count=0,
        )
        db.add(unresolved)
        db.flush()

        repo = UnresolvedLocationQueryRepository(db)
        for _ in range(5):
            repo.record_click(query, region_boundary_id=str(region.id), original_query=query)

        unresolved.search_count = 5
        db.flush()

        service = AliasLearningService(db, region_code=region_type)
        learned = service.process_pending(limit=10)

        assert len(learned) == 1
        assert learned[0].alias_normalized == query

    def test_skips_non_pending_rows(self, db):
        row = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=f"learned {ULID()}".lower(),
            sample_original_queries=[],
            search_count=10,
            unique_user_count=10,
            status="learned",
        )

        service = AliasLearningService(db)

        assert service._learn_from_row(row) is None

    def test_skips_when_counts_invalid(self, db):
        row = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=f"invalid {ULID()}".lower(),
            sample_original_queries=[],
            search_count=10,
            unique_user_count=10,
            status="pending",
            click_count=5,
            click_region_counts=[],
        )

        service = AliasLearningService(db)

        assert service._learn_from_row(row) is None

    def test_skips_when_total_clicks_below_min(self, db):
        row = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=f"lowclicks {ULID()}".lower(),
            sample_original_queries=[],
            search_count=10,
            unique_user_count=10,
            status="pending",
            click_count=0,
            click_region_counts={"region-1": 1},
        )

        service = AliasLearningService(db)

        assert service._learn_from_row(row) is None

    def test_skips_when_no_top_region(self, db):
        row = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=f"noregion {ULID()}".lower(),
            sample_original_queries=[],
            search_count=10,
            unique_user_count=10,
            status="pending",
            click_count=7,
            click_region_counts={None: 5, "": 2},
        )

        service = AliasLearningService(db)

        assert service._learn_from_row(row) is None

    def test_skips_when_search_count_too_low(self, db):
        row = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=f"searchlow {ULID()}".lower(),
            sample_original_queries=[],
            search_count=1,
            unique_user_count=1,
            status="pending",
            click_count=0,
            click_region_counts={"region-ok": 3, "region-bad": "bad"},
        )

        service = AliasLearningService(db)

        assert service._learn_from_row(row) is None

    def test_skips_when_confidence_too_low(self, db):
        row = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=f"confidence {ULID()}".lower(),
            sample_original_queries=[],
            search_count=10,
            unique_user_count=10,
            status="pending",
            click_count=0,
            click_region_counts={"region-a": 2, "region-b": 2},
        )

        service = AliasLearningService(db)

        assert service._learn_from_row(row) is None

    def test_skips_when_region_missing(self, db):
        row = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=f"missing-region {ULID()}".lower(),
            sample_original_queries=[],
            search_count=10,
            unique_user_count=10,
            status="pending",
            click_count=5,
            click_region_counts={"missing-region": 5},
        )

        service = AliasLearningService(db, region_code="test-missing")

        assert service._learn_from_row(row) is None

    def test_existing_alias_marks_manual_review(self, db):
        region_type = f"test-{ULID()}".lower()
        region = _create_region(
            db,
            region_type=region_type,
            region_name="SoHo",
            parent_region="Manhattan",
        )
        query = f"existing {ULID()}".lower()

        db.add(
            LocationAlias(
                alias_normalized=query,
                region_boundary_id=str(region.id),
                status="active",
                confidence=1.0,
                user_count=2,
                source="manual",
            )
        )
        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=query,
            sample_original_queries=[query],
            search_count=10,
            unique_user_count=10,
            status="pending",
            click_count=5,
            click_region_counts={str(region.id): 5},
        )
        db.add(unresolved)
        db.flush()

        service = AliasLearningService(db, region_code=region_type)
        learned = service._learn_from_row(unresolved)

        assert learned is None
        assert unresolved.status == "manual_review"

    def test_add_failure_returns_none(self, db, monkeypatch):
        region_type = f"test-{ULID()}".lower()
        region = _create_region(
            db,
            region_type=region_type,
            region_name="East Village",
            parent_region="Manhattan",
        )
        existing_alias = LocationAlias(
            id=str(ULID()),
            alias_normalized=f"existing-alias {ULID()}".lower(),
            region_boundary_id=str(region.id),
            status="active",
            confidence=1.0,
            user_count=1,
            source="manual",
        )
        db.add(existing_alias)
        db.flush()
        db.expunge(existing_alias)

        query = f"alias-fail {ULID()}".lower()
        unresolved = UnresolvedLocationQuery(
            city_id="01JDEFAULTNYC0000000000",
            query_normalized=query,
            sample_original_queries=[query],
            search_count=10,
            unique_user_count=10,
            status="pending",
            click_count=5,
            click_region_counts={str(region.id): 5},
        )
        db.add(unresolved)
        db.flush()

        monkeypatch.setattr(
            "app.services.search.alias_learning_service.generate_ulid",
            lambda: existing_alias.id,
        )

        service = AliasLearningService(db, region_code=region_type)
        learned = service._learn_from_row(unresolved)

        assert learned is None
