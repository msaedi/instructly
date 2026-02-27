from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.repositories.bulk_operation_repository import BulkOperationRepository


class TestBulkOperationRepositoryCoverage:
    def test_has_bookings_on_date_true(self, db, test_booking):
        repo = BulkOperationRepository(db)

        result = repo.has_bookings_on_date(
            instructor_id=test_booking.instructor_id, target_date=test_booking.booking_date
        )

        assert result is True

    def test_has_bookings_on_date_false(self, db, test_booking):
        repo = BulkOperationRepository(db)
        missing_date = test_booking.booking_date + timedelta(days=7)

        result = repo.has_bookings_on_date(
            instructor_id=test_booking.instructor_id, target_date=missing_date
        )

        assert result is False

    def test_has_bookings_on_date_error(self):
        mock_db = MagicMock()
        mock_db.query.side_effect = SQLAlchemyError("boom")

        repo = BulkOperationRepository(mock_db)
        with pytest.raises(RepositoryException):
            repo.has_bookings_on_date("inst", target_date=None)  # type: ignore[arg-type]
