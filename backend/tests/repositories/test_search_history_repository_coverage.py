from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.search_history import SearchHistory
from app.models.user import User
from app.repositories.search_history_repository import SearchHistoryRepository
from app.schemas.search_context import SearchUserContext


def _make_user(db: Session, *, prefix: str) -> User:
    user = User(
        email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
        first_name="Test",
        last_name="User",
        phone="+12125550000",
        zip_code="10001",
    )
    db.add(user)
    db.commit()
    return user


def _clear_search_history(db: Session) -> None:
    db.query(SearchHistory).delete()
    db.commit()


def test_increment_search_count_updates_and_skips_deleted(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="increment")

    search = SearchHistory(
        user_id=user.id,
        search_query="piano lessons",
        normalized_query="piano lessons",
        search_type="natural_language",
        search_count=1,
        first_searched_at=datetime.now(timezone.utc) - timedelta(days=1),
        last_searched_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(search)
    db.commit()

    updated = repo.increment_search_count(search.id)
    assert updated is not None
    assert updated.search_count == 2

    search.deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert repo.increment_search_count(search.id) is None
    assert repo.increment_search_count("missing") is None


def test_find_existing_search_for_update_user_and_guest(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="existing")
    guest_id = f"guest-{uuid.uuid4().hex[:8]}"

    user_search = SearchHistory(
        user_id=user.id,
        search_query="Yoga",
        normalized_query="yoga",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    guest_search = SearchHistory(
        guest_session_id=guest_id,
        search_query="Piano",
        normalized_query="piano",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    db.add_all([user_search, guest_search])
    db.commit()

    found_user = repo.find_existing_search_for_update(
        user_id=user.id, search_query="  Yoga  "
    )
    assert found_user is not None
    assert found_user.id == user_search.id

    found_guest = repo.find_existing_search_for_update(
        guest_session_id=guest_id, search_query="piano"
    )
    assert found_guest is not None
    assert found_guest.id == guest_search.id

    assert repo.find_existing_search_for_update(user_id=user.id, search_query=None) is None
    assert repo.find_existing_search_for_update(search_query="x") is None


def test_get_recent_searches_unified_orders(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    guest_id = f"recent-{uuid.uuid4().hex[:8]}"
    base_time = datetime.now(timezone.utc)

    searches = [
        SearchHistory(
            guest_session_id=guest_id,
            search_query=f"query {i}",
            normalized_query=f"query {i}",
            search_type="natural_language",
            first_searched_at=base_time - timedelta(hours=i),
            last_searched_at=base_time - timedelta(hours=i),
        )
        for i in range(3)
    ]
    db.add_all(searches)
    db.commit()

    context = SearchUserContext.from_guest(guest_id)
    by_first = repo.get_recent_searches_unified(context, limit=2, order_by="first_searched_at")
    assert [item.search_query for item in by_first] == ["query 0", "query 1"]

    fallback = repo.get_recent_searches_unified(context, limit=1, order_by="unknown")
    assert fallback[0].search_query == "query 0"


def test_soft_delete_guest_search_and_get_user_searches(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    guest_id = f"guest-delete-{uuid.uuid4().hex[:8]}"
    user = _make_user(db, prefix="user-searches")

    guest_search = SearchHistory(
        guest_session_id=guest_id,
        search_query="guest",
        normalized_query="guest",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    user_search = SearchHistory(
        user_id=user.id,
        search_query="active",
        normalized_query="active",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    deleted_search = SearchHistory(
        user_id=user.id,
        search_query="deleted",
        normalized_query="deleted",
        search_type="natural_language",
        deleted_at=datetime.now(timezone.utc),
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    db.add_all([guest_search, user_search, deleted_search])
    db.commit()

    assert repo.soft_delete_guest_search(guest_search.id, guest_id) is True

    active_only = repo.get_user_searches(user.id)
    assert [search.search_query for search in active_only] == ["active"]

    all_searches = repo.get_user_searches(user.id, exclude_deleted=False)
    assert {search.search_query for search in all_searches} == {"active", "deleted"}


def test_delete_user_searches_and_counts(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="delete-user")

    db.add_all(
        [
            SearchHistory(
                user_id=user.id,
                search_query="one",
                normalized_query="one",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
            SearchHistory(
                user_id=user.id,
                search_query="two",
                normalized_query="two",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db.commit()

    total_before = repo.count_all_searches()
    deleted = repo.delete_user_searches(user.id)
    db.commit()
    assert deleted == 2
    assert repo.count_all_searches() == total_before - 2


def test_upsert_search_and_get_search_by_user_and_query(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="upsert-user")
    guest_id = f"guest-upsert-{uuid.uuid4().hex[:8]}"

    result = repo.upsert_search(
        user_id=user.id,
        search_query="Piano",
        normalized_query="piano",
        search_type="natural_language",
        results_count=3,
    )
    assert result is not None
    assert result.search_count == 1

    updated = repo.upsert_search(
        user_id=user.id,
        search_query="Piano lessons",
        normalized_query="piano",
        search_type="natural_language",
        results_count=5,
    )
    assert updated is not None
    assert updated.search_count == 2
    assert updated.search_query == "Piano lessons"

    guest = repo.upsert_search(
        guest_session_id=guest_id,
        search_query="Yoga",
        normalized_query="yoga",
        search_type="natural_language",
        results_count=2,
    )
    assert guest is not None
    assert guest.guest_session_id == guest_id

    fetched = repo.get_search_by_user_and_query(
        user_id=user.id, normalized_query="piano"
    )
    assert fetched is not None
    assert fetched.search_count == 2


def test_enforce_search_limit_and_cleanup_counts(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    guest_id = f"limit-{uuid.uuid4().hex[:8]}"
    base_time = datetime.now(timezone.utc) - timedelta(days=5)

    for i in range(5):
        db.add(
            SearchHistory(
                guest_session_id=guest_id,
                search_query=f"old {i}",
                normalized_query=f"old {i}",
                search_type="natural_language",
                first_searched_at=base_time - timedelta(days=i),
                last_searched_at=base_time - timedelta(days=i),
            )
        )
    db.commit()

    deleted = repo.enforce_search_limit(guest_session_id=guest_id, max_searches=2)
    db.commit()
    assert deleted == 3


def test_counts_and_soft_delete_by_id(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="count-user")

    search = SearchHistory(
        user_id=user.id,
        search_query="count",
        normalized_query="count",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    db.add(search)
    db.commit()

    assert repo.count_searches(user_id=user.id) == 1
    assert repo.count_searches() == 0

    assert repo.soft_delete_by_id(search.id, user.id) is True
    assert repo.soft_delete_by_id("missing", user.id) is False


def test_find_analytics_eligible_searches_filters(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="analytics")

    guest_search = SearchHistory(
        guest_session_id="guest-analytics",
        search_query="guest",
        normalized_query="guest",
        search_type="natural_language",
        converted_to_user_id=user.id,
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    user_search = SearchHistory(
        user_id=user.id,
        search_query="user",
        normalized_query="user",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    deleted_search = SearchHistory(
        user_id=user.id,
        search_query="deleted",
        normalized_query="deleted",
        search_type="natural_language",
        deleted_at=datetime.now(timezone.utc),
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    db.add_all([guest_search, user_search, deleted_search])
    db.commit()

    rows = repo.find_analytics_eligible_searches(include_deleted=False).all()
    ids = {row.id for row in rows}
    assert user_search.id in ids
    assert guest_search.id not in ids
    assert deleted_search.id not in ids

    assert repo.count_soft_deleted_total() == 1
    assert repo.count_soft_deleted_eligible(days_old=1) == 0


def test_guest_cleanup_stats_and_deletions(db: Session) -> None:
    repo = SearchHistoryRepository(db)
    guest_id = f"cleanup-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    converted_user = _make_user(db, prefix="converted")

    db.add_all(
        [
            SearchHistory(
                guest_session_id=guest_id,
                search_query="converted",
                normalized_query="converted",
                search_type="natural_language",
                converted_to_user_id=converted_user.id,
                converted_at=now - timedelta(days=10),
                first_searched_at=now - timedelta(days=20),
                last_searched_at=now - timedelta(days=20),
            ),
            SearchHistory(
                guest_session_id=guest_id,
                search_query="expired",
                normalized_query="expired",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=30),
                last_searched_at=now - timedelta(days=30),
            ),
        ]
    )
    db.commit()

    assert repo.count_total_guest_sessions() >= 2
    assert repo.count_converted_guest_eligible(days_old=5) >= 1
    assert repo.count_expired_guest_eligible(days_old=5) >= 1

    assert repo.delete_converted_guest_searches(days_old=5) >= 1
    assert repo.delete_old_unconverted_guest_searches(days_old=5) >= 1


def test_misc_helpers_return_none_or_counts(db: Session) -> None:
    repo = SearchHistoryRepository(db)

    assert repo.get_previous_search_event() is None
    assert repo.get_search_event_by_id(event_id=123) is None

    old_deleted = SearchHistory(
        guest_session_id=f"hard-delete-{uuid.uuid4().hex[:8]}",
        search_query="deleted",
        normalized_query="deleted",
        search_type="natural_language",
        deleted_at=datetime.now(timezone.utc) - timedelta(days=10),
        first_searched_at=datetime.now(timezone.utc) - timedelta(days=11),
        last_searched_at=datetime.now(timezone.utc) - timedelta(days=11),
    )
    db.add(old_deleted)
    db.commit()

    deleted_count = repo.hard_delete_old_soft_deleted(days_old=5)
    db.commit()
    assert deleted_count >= 1


def test_add_user_filter_requires_identifier(db: Session) -> None:
    repo = SearchHistoryRepository(db)
    query = repo.db.query(SearchHistory)
    with pytest.raises(ValueError):
        repo._add_user_filter(query, SimpleNamespace(user_id=None, guest_session_id=None))


def test_find_existing_search_variants(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="find-existing")
    guest_id = f"guest-{uuid.uuid4().hex[:8]}"

    user_search = SearchHistory(
        user_id=user.id,
        search_query="Yoga",
        normalized_query="yoga",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    guest_search = SearchHistory(
        guest_session_id=guest_id,
        search_query="Yoga",
        normalized_query="yoga",
        search_type="natural_language",
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    db.add_all([user_search, guest_search])
    db.commit()

    assert repo.find_existing_search(user_id=user.id, query="Yoga").id == user_search.id
    assert (
        repo.find_existing_search(guest_session_id=guest_id, query="Yoga").id == guest_search.id
    )
    assert repo.find_existing_search(user_id=user.id, query=None) is None
    assert repo.find_existing_search(query="Yoga") is None


def test_recent_searches_and_counts_for_guest(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    guest_id = f"guest-recent-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    db.add_all(
        [
            SearchHistory(
                guest_session_id=guest_id,
                search_query="old",
                normalized_query="old",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=1),
                last_searched_at=now - timedelta(days=1),
            ),
            SearchHistory(
                guest_session_id=guest_id,
                search_query="new",
                normalized_query="new",
                search_type="natural_language",
                first_searched_at=now,
                last_searched_at=now,
            ),
        ]
    )
    db.commit()

    recent = repo.get_recent_searches(guest_session_id=guest_id, limit=1)
    assert recent[0].search_query == "new"
    assert repo.get_recent_searches() == []
    assert repo.count_searches(guest_session_id=guest_id) == 2
    assert repo.count_searches() == 0


def test_get_recent_searches_unified_last_searched(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="recent-last")
    now = datetime.now(timezone.utc)

    db.add_all(
        [
            SearchHistory(
                user_id=user.id,
                search_query="older",
                normalized_query="older",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=1),
                last_searched_at=now - timedelta(days=1),
            ),
            SearchHistory(
                user_id=user.id,
                search_query="newer",
                normalized_query="newer",
                search_type="natural_language",
                first_searched_at=now,
                last_searched_at=now,
            ),
        ]
    )
    db.commit()

    context = SearchUserContext.from_user(user.id)
    recent = repo.get_recent_searches_unified(context, limit=1, order_by="last_searched_at")
    assert recent[0].search_query == "newer"


def test_searches_to_delete_and_soft_delete_old(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="keep")

    db.add_all(
        [
            SearchHistory(
                user_id=user.id,
                search_query="a",
                normalized_query="a",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            ),
            SearchHistory(
                user_id=user.id,
                search_query="b",
                normalized_query="b",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc) - timedelta(days=1),
                last_searched_at=datetime.now(timezone.utc) - timedelta(days=1),
            ),
        ]
    )
    db.commit()

    empty_subquery = repo.get_searches_to_delete()
    assert repo.soft_delete_old_searches(keep_ids_subquery=None) == 0
    assert repo.soft_delete_old_searches(keep_ids_subquery=empty_subquery) == 0

    keep_ids = repo.get_searches_to_delete(user_id=user.id, keep_count=1)
    assert repo.soft_delete_old_searches(user_id=user.id, keep_ids_subquery=keep_ids) == 1


def test_create_and_conversion_helpers(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="convert")
    guest_id = f"guest-convert-{uuid.uuid4().hex[:8]}"

    created = repo.create(
        user_id=user.id,
        search_query=" Mixed Case ",
        normalized_query=None,
        search_type="natural_language",
    )
    db.commit()
    assert created.normalized_query == "mixed case"

    db.add_all(
        [
            SearchHistory(
                guest_session_id=guest_id,
                search_query="first",
                normalized_query="first",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc) - timedelta(days=2),
                last_searched_at=datetime.now(timezone.utc) - timedelta(days=2),
            ),
            SearchHistory(
                guest_session_id=guest_id,
                search_query="second",
                normalized_query="second",
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc) - timedelta(days=1),
                last_searched_at=datetime.now(timezone.utc) - timedelta(days=1),
            ),
        ]
    )
    db.commit()

    ordered = repo.get_guest_searches_for_conversion(guest_id)
    assert [row.search_query for row in ordered] == ["first", "second"]

    assert repo.mark_searches_as_converted(guest_id, user.id) == 2


def test_find_analytics_eligible_date_filters(db: Session) -> None:
    _clear_search_history(db)
    repo = SearchHistoryRepository(db)
    user = _make_user(db, prefix="date-filter")
    now = datetime.now(timezone.utc)

    db.add_all(
        [
            SearchHistory(
                user_id=user.id,
                search_query="old",
                normalized_query="old",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=10),
                last_searched_at=now - timedelta(days=10),
            ),
            SearchHistory(
                user_id=user.id,
                search_query="recent",
                normalized_query="recent",
                search_type="natural_language",
                first_searched_at=now - timedelta(days=1),
                last_searched_at=now - timedelta(days=1),
            ),
        ]
    )
    db.commit()

    rows = repo.find_analytics_eligible_searches(
        start_date=now - timedelta(days=2), end_date=now
    ).all()
    assert {row.search_query for row in rows} == {"recent"}


def test_get_search_by_user_and_query_empty(db: Session) -> None:
    repo = SearchHistoryRepository(db)
    assert repo.get_search_by_user_and_query(normalized_query="missing") is None
