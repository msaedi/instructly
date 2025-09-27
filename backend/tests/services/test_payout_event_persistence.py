"""
Tests that payout webhooks persist analytics rows per instructor.
"""

from unittest.mock import patch

import ulid

from app.models.instructor import InstructorProfile
from app.models.payment import InstructorPayoutEvent
from app.models.user import User
from app.services.stripe_service import StripeService


def test_payout_persistence_created_paid_failed(db):
    # Seed a connected account mapping
    service = StripeService(db)

    # Create instructor/profile and mock connected account repo response
    user = User(
        id=str(ulid.ULID()),
        email=f"ins_{ulid.ULID()}@example.com",
        hashed_password="x",
        first_name="I",
        last_name="N",
        is_active=True,
        zip_code="10001",
    )
    db.add(user)
    db.flush()
    profile = InstructorProfile(id=str(ulid.ULID()), user_id=user.id)
    db.add(profile)
    db.flush()

    fake_account_id = "acct_123"

    class FakeAcct:
        def __init__(self, instructor_profile_id):
            self.instructor_profile_id = instructor_profile_id

    with patch.object(
        service.payment_repository, "get_connected_account_by_stripe_id", return_value=FakeAcct(profile.id)
    ):
        created = {
            "type": "payout.created",
            "data": {"object": {"id": "po_1", "amount": 100, "destination": fake_account_id}},
        }
        paid = {
            "type": "payout.paid",
            "data": {"object": {"id": "po_2", "amount": 200, "destination": fake_account_id}},
        }
        failed = {
            "type": "payout.failed",
            "data": {
                "object": {
                    "id": "po_3",
                    "amount": 300,
                    "destination": fake_account_id,
                    "failure_code": "acct",
                    "failure_message": "invalid",
                }
            },
        }

        assert service._handle_payout_webhook(created)
        assert service._handle_payout_webhook(paid)
        assert service._handle_payout_webhook(failed)

    # Verify rows exist
    rows = db.query(InstructorPayoutEvent).all()
    assert len(rows) >= 3
    ids = {r.payout_id for r in rows}
    assert {"po_1", "po_2", "po_3"}.issubset(ids)
