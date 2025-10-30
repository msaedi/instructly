from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.booking_repository import BookingRepository
from app.repositories.service_catalog_repository import ServiceCatalogRepository


@pytest.mark.integration
def test_repository_constructors_are_passive() -> None:
    session = MagicMock(spec=Session)

    AvailabilityRepository(session)
    BookingRepository(session)
    ServiceCatalogRepository(session)

    assert not session.query.called
    execute_calls = session.execute.call_args_list
    assert len(execute_calls) <= 1
    if execute_calls:
        sql_text = str(execute_calls[0].args[0])
        assert "pg_extension" in sql_text


@pytest.mark.integration
def test_repository_transaction_context_manages_commit_and_rollback() -> None:
    session = MagicMock(spec=Session)
    repo = AvailabilityRepository(session)

    with repo.transaction() as transactional_session:
        transactional_session.add("placeholder")

    session.commit.assert_called_once()
    session.rollback.assert_not_called()

    session.commit.reset_mock()
    session.rollback.reset_mock()

    with pytest.raises(RuntimeError):
        with repo.transaction():
            raise RuntimeError("boom")

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
