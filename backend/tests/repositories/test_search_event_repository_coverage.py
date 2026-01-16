from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.models.search_event import SearchEvent, SearchEventCandidate
from app.models.search_interaction import SearchInteraction
from app.models.service_catalog import ServiceCatalog
from app.repositories.search_event_repository import SearchEventRepository


def _create_event(db, **kwargs) -> SearchEvent:
    event = SearchEvent(**kwargs)
    db.add(event)
    db.flush()
    return event


def _get_catalog_id(db) -> str | None:
    entry = (
        db.execute(select(ServiceCatalog).limit(1))
        .scalars()
        .first()
    )
    return entry.id if entry else None


class TestSearchEventRepositoryCoverage:
    def test_create_event_and_candidates(self, db, test_student):
        repo = SearchEventRepository(db)

        event_from_dict = repo.create_event(
            event_data={"search_query": "piano", "search_type": "natural_language"}
        )
        event_from_kwargs = repo.create_event(
            search_query="guitar", search_type="category", results_count=4
        )

        assert event_from_dict.id is not None
        assert event_from_kwargs.search_query == "guitar"

        assert repo.bulk_insert_candidates(event_from_kwargs.id, []) == 0

        catalog_id = _get_catalog_id(db)
        candidates = [
            {
                "position": 1,
                "service_catalog_id": catalog_id,
                "score": 0.9,
                "vector_score": 0.5,
                "lexical_score": 0.4,
                "source": "hybrid",
            }
        ]
        inserted = repo.bulk_insert_candidates(event_from_kwargs.id, candidates)
        assert inserted == 1
        assert (
            db.query(SearchEventCandidate)
            .filter(SearchEventCandidate.search_event_id == event_from_kwargs.id)
            .count()
            == 1
        )

    def test_popular_searches_and_avg_results(self, db, test_student):
        repo = SearchEventRepository(db)
        now = datetime.now(timezone.utc)

        _create_event(
            db,
            user_id=test_student.id,
            search_query="piano",
            search_type="natural_language",
            results_count=3,
            searched_at=now - timedelta(hours=1),
        )
        _create_event(
            db,
            user_id=test_student.id,
            search_query="piano",
            search_type="natural_language",
            results_count=7,
            searched_at=now - timedelta(hours=2),
        )
        _create_event(
            db,
            user_id=test_student.id,
            search_query="guitar",
            search_type="category",
            results_count=1,
            searched_at=now - timedelta(hours=2),
        )
        db.commit()

        popular = repo.get_popular_searches(limit=1000, days=1)
        assert any(item["query"] == "piano" for item in popular)

        avg_results = repo.get_popular_searches_with_avg_results(limit=1000, hours=6)
        assert any(item["query"] == "piano" for item in avg_results)

    def test_quality_score_and_interactions(self, db, test_student):
        repo = SearchEventRepository(db)
        now = datetime.now(timezone.utc)

        zero_event = _create_event(
            db,
            user_id=test_student.id,
            search_query="zero",
            search_type="natural_language",
            results_count=0,
            searched_at=now,
        )
        good_event = _create_event(
            db,
            user_id=test_student.id,
            search_query="good",
            search_type="natural_language",
            results_count=5,
            searched_at=now,
        )
        big_event = _create_event(
            db,
            user_id=test_student.id,
            search_query="big",
            search_type="natural_language",
            results_count=75,
            searched_at=now,
        )
        db.flush()

        db.add(
            SearchInteraction(
                search_event_id=good_event.id,
                interaction_type="click",
            )
        )
        db.commit()

        assert repo.calculate_search_quality_score(zero_event.id) == 0.0
        assert repo.calculate_search_quality_score(good_event.id) > 0.0
        assert repo.calculate_search_quality_score(big_event.id) >= 30.0

    def test_user_session_queries_and_previous_event(self, db, test_student):
        repo = SearchEventRepository(db)
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(hours=2)

        first = _create_event(
            db,
            user_id=test_student.id,
            search_query="first",
            search_type="natural_language",
            results_count=2,
            searched_at=earlier,
        )
        _create_event(
            db,
            user_id=test_student.id,
            search_query="second",
            search_type="natural_language",
            results_count=2,
            searched_at=now,
        )
        guest_session_id = str(uuid4())
        guest_event = _create_event(
            db,
            session_id=guest_session_id,
            guest_session_id=guest_session_id,
            search_query="guest",
            search_type="filter",
            results_count=1,
            searched_at=now - timedelta(minutes=1),
        )
        db.commit()

        assert repo.get_searches_by_user(test_student.id, limit=1)
        assert repo.get_searches_by_session(guest_session_id)

        previous = repo.get_previous_search_event(user_id=test_student.id, before_time=now)
        assert previous is not None
        assert previous.id == first.id

        previous_guest = repo.get_previous_search_event(
            guest_session_id=guest_session_id, before_time=now
        )
        assert previous_guest is not None
        assert previous_guest.id == guest_event.id

        assert repo.get_previous_search_event() is None

    def test_search_patterns_and_counts(self, db, test_student):
        repo = SearchEventRepository(db)
        now = datetime.now(timezone.utc)

        _create_event(
            db,
            user_id=test_student.id,
            search_query="pattern",
            search_type="natural_language",
            results_count=4,
            searched_at=now - timedelta(days=1),
        )
        _create_event(
            db,
            user_id=test_student.id,
            search_query="pattern",
            search_type="category",
            results_count=6,
            searched_at=now,
        )
        db.commit()

        distribution = repo.get_search_type_distribution(hours=72)
        assert distribution.get("natural_language")

        patterns = repo.get_search_patterns("pattern", days=7)
        assert patterns["query"] == "pattern"
        assert patterns["period_days"] == 7
        assert patterns["daily_counts"]

        since_count = repo.count_searches_since(now - timedelta(days=2))
        assert since_count >= 2

    def test_delete_old_events_and_hourly_counts(self, db, test_student):
        repo = SearchEventRepository(db)
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=10)

        _create_event(
            db,
            user_id=test_student.id,
            search_query="old",
            search_type="natural_language",
            results_count=1,
            searched_at=old,
        )
        _create_event(
            db,
            user_id=test_student.id,
            search_query="recent",
            search_type="natural_language",
            results_count=1,
            searched_at=now - timedelta(hours=1),
        )
        db.commit()

        assert repo.count_old_events(now - timedelta(days=5)) >= 1
        deleted = repo.delete_old_events(now - timedelta(days=5))
        assert deleted >= 1

        hourly = repo.get_hourly_search_counts(now - timedelta(days=1), limit=5)
        assert isinstance(hourly, list)

    def test_user_events_delete_and_counts(self, db, test_student, test_instructor):
        repo = SearchEventRepository(db)
        now = datetime.now(timezone.utc)

        _create_event(
            db,
            user_id=test_student.id,
            search_query="user-one",
            search_type="natural_language",
            results_count=1,
            searched_at=now,
        )
        _create_event(
            db,
            user_id=test_student.id,
            search_query="user-two",
            search_type="natural_language",
            results_count=1,
            searched_at=now - timedelta(minutes=10),
        )
        _create_event(
            db,
            user_id=test_instructor.id,
            search_query="other",
            search_type="natural_language",
            results_count=1,
            searched_at=now,
        )
        db.commit()

        events = repo.get_user_events(test_student.id)
        assert len(events) >= 2
        assert repo.count_all_events() >= 3

        deleted = repo.delete_user_events(test_student.id)
        assert deleted >= 2

    def test_search_distributions_and_interactions(self, db, test_student):
        repo = SearchEventRepository(db)
        now = datetime.now(timezone.utc)

        event = _create_event(
            db,
            user_id=test_student.id,
            search_query="dist",
            search_type="natural_language",
            results_count=2,
            searched_at=now,
        )
        db.add(
            SearchInteraction(
                search_event_id=event.id,
                interaction_type="click",
            )
        )
        db.commit()

        distribution = repo.get_search_type_distribution()
        assert distribution.get("natural_language") is not None

        count_with_interactions = repo.count_searches_with_interactions(now - timedelta(days=1))
        assert count_with_interactions >= 1

        results_all_time = repo.get_popular_searches_with_avg_results(limit=10, hours=None)
        assert any(item["query"] == "dist" for item in results_all_time)

        no_limit = repo.get_searches_by_user(test_student.id)
        assert no_limit

        event_by_id = repo.get_search_event_by_id(event.id)
        assert event_by_id is not None
