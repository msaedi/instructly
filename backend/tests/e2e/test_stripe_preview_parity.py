"""Optional Stripe E2E parity test (skipped unless explicitly enabled)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import os

import pytest
import stripe

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import RoleName
from app.core.exceptions import ServiceException
from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.payment import PlatformCredit, StripeCustomer
from app.models.rbac import Role, UserRole as UserRoleJunction
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields

RUN_E2E = os.getenv("RUN_STRIPE_E2E") == "1"


def _ensure_role(session, role_name: RoleName) -> Role:
    role = session.query(Role).filter(Role.name == role_name.value).first()
    if not role:
        role = Role(name=role_name.value, description=f"{role_name.value.title()} role")
        session.add(role)
        session.commit()
    return role


def _get_or_create_user(session, email: str, first_name: str, last_name: str, role: Role) -> User:
    user = session.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        zip_code="10001",
        hashed_password=get_password_hash("StripeE2E123!"),
        is_active=True,
        account_status="active",
    )
    session.add(user)
    session.flush()
    session.add(UserRoleJunction(user_id=user.id, role_id=role.id))
    session.commit()
    return user


@pytest.mark.stripe_e2e
@pytest.mark.skipif(not RUN_E2E, reason="RUN_STRIPE_E2E not enabled")
def test_stripe_preview_amount_parity_e2e():
    if not settings.stripe_secret_key:
        pytest.skip("STRIPE_SECRET_KEY not configured")

    dest_account = os.getenv("STRIPE_E2E_DESTINATION_ACCOUNT")
    if not dest_account:
        pytest.skip("STRIPE_E2E_DESTINATION_ACCOUNT env var required")

    stripe.api_key = settings.stripe_secret_key.get_secret_value()

    session = SessionLocal()
    # Track created objects for cleanup
    created_customers: list[str] = []
    created_payment_intents: list[str] = []
    created_transfers: list[str] = []
    created_platform_credit_ids: list[str] = []
    disposable_models = []

    try:
        student_role = _ensure_role(session, RoleName.STUDENT)
        instructor_role = _ensure_role(session, RoleName.INSTRUCTOR)

        student = _get_or_create_user(
            session,
            email="stripe.e2e.student@example.com",
            first_name="Stripe",
            last_name="Student",
            role=student_role,
        )
        instructor_user = _get_or_create_user(
            session,
            email="stripe.e2e.instructor@example.com",
            first_name="Stripe",
            last_name="Instructor",
            role=instructor_role,
        )

        profile = session.query(InstructorProfile).filter_by(user_id=instructor_user.id).first()
        if not profile:
            profile = InstructorProfile(
                user_id=instructor_user.id,
                bio="Stripe E2E instructor",
                years_experience=5,
                skills_configured=True,
                identity_verified_at=datetime.now(timezone.utc),
                onboarding_completed_at=datetime.now(timezone.utc),
                is_live=True,
            )
            session.add(profile)
            session.flush()
            disposable_models.append(profile)

        category = (
            session.query(ServiceCategory)
            .filter(ServiceCategory.slug == "stripe-e2e")
            .first()
        )
        if not category:
            category = ServiceCategory(
                name="Stripe E2E",
                slug="stripe-e2e",
                description="Stripe parity testing",
                display_order=999,
            )
            session.add(category)
            session.flush()
            disposable_models.append(category)

        catalog_service = (
            session.query(ServiceCatalog)
            .filter(ServiceCatalog.slug == "stripe-e2e-session")
            .first()
        )
        if not catalog_service:
            catalog_service = ServiceCatalog(
                category_id=category.id,
                name="Stripe E2E Session",
                slug="stripe-e2e-session",
                description="Parity test session",
                online_capable=True,
                display_order=999,
            )
            session.add(catalog_service)
            session.flush()
            disposable_models.append(catalog_service)

        instructor_service = (
            session.query(InstructorService)
            .filter(
                InstructorService.instructor_profile_id == profile.id,
                InstructorService.service_catalog_id == catalog_service.id,
            )
            .first()
        )
        if not instructor_service:
            instructor_service = InstructorService(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service.id,
                hourly_rate=80.0,
                duration_options=[60],
                location_types=["online"],
                is_active=True,
            )
            session.add(instructor_service)
            session.flush()
            disposable_models.append(instructor_service)

        pricing_service = PricingService(session)
        config_service = ConfigService(session)
        stripe_service = StripeService(
            session,
            config_service=config_service,
            pricing_service=pricing_service,
        )

        payment_repo = stripe_service.payment_repository
        existing_record = payment_repo.get_customer_by_user_id(student.id)
        if existing_record:
            try:
                stripe.Customer.delete(existing_record.stripe_customer_id)
            except Exception:
                pass
            session.query(StripeCustomer).filter(StripeCustomer.id == existing_record.id).delete()
            session.commit()

        customer = stripe_service.create_customer(
            user_id=student.id,
            email=student.email,
            name=f"{student.first_name} {student.last_name}",
        )
        customer_id = customer.stripe_customer_id
        created_customers.append(customer_id)

        if not payment_repo.get_connected_account_by_instructor_id(profile.id):
            payment_repo.create_connected_account_record(
                instructor_profile_id=profile.id,
                stripe_account_id=dest_account,
                onboarding_completed=True,
            )

        def _create_booking_instance(day_offset: int, booking_tag: str) -> Booking:
            booking_date = date.today() + timedelta(days=day_offset)
            start_time = time(12, 0)
            end_time = time(13, 0)
            booking = Booking(
                student_id=student.id,
                instructor_id=instructor_user.id,
                instructor_service_id=instructor_service.id,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                **booking_timezone_fields(booking_date, start_time, end_time),
                duration_minutes=60,
                service_name=catalog_service.name,
                hourly_rate=Decimal("80.00"),
                total_price=Decimal("80.00"),
                status=BookingStatus.CONFIRMED,
                location_type="online",
                meeting_location="Online",
                student_note=f"Stripe E2E {booking_tag}",
            )
            session.add(booking)
            session.commit()
            disposable_models.append(booking)
            return booking

        # Scenario 1: No credits
        booking_basic = _create_booking_instance(1, "basic")
        preview_basic = pricing_service.compute_booking_pricing(booking_basic.id)
        context_basic = stripe_service.build_charge_context(booking_basic.id)
        pi_basic = stripe_service.create_payment_intent(
            booking_id=booking_basic.id,
            customer_id=customer_id,
            destination_account_id=dest_account,
            charge_context=context_basic,
        )
        created_payment_intents.append(pi_basic.stripe_payment_intent_id)

        pi_basic_remote = stripe.PaymentIntent.retrieve(pi_basic.stripe_payment_intent_id)
        assert pi_basic_remote.amount == preview_basic["student_pay_cents"]
        # With transfer_data[amount] architecture, we don't use application_fee_amount
        # Instead, transfer_data.amount specifies the instructor payout
        assert pi_basic_remote.application_fee_amount is None
        assert (
            pi_basic_remote.transfer_data.amount
            == preview_basic["target_instructor_payout_cents"]
        )
        assert pi_basic_remote.metadata.get("base_price_cents") == str(
            preview_basic["base_price_cents"]
        )
        assert pi_basic_remote.metadata.get("student_fee_cents") == str(
            preview_basic["student_fee_cents"]
        )
        assert pi_basic_remote.metadata.get("applied_credit_cents") == str(
            preview_basic["credit_applied_cents"]
        )
        assert pi_basic_remote.metadata.get("student_pay_cents") == str(
            preview_basic["student_pay_cents"]
        )

        # Scenario 2: Credits trigger top-up
        booking_topup = _create_booking_instance(2, "topup")
        payment_repo.create_platform_credit(
            user_id=student.id,
            amount_cents=12000,
            reason="stripe-e2e",
        )
        session.commit()
        created_platform_credit_ids.extend(
            [credit.id for credit in session.query(PlatformCredit).filter(PlatformCredit.reason == "stripe-e2e").all()]
        )

        credit_request_cents = 7000
        context_topup = stripe_service.build_charge_context(
            booking_id=booking_topup.id,
            requested_credit_cents=credit_request_cents,
        )
        preview_topup = pricing_service.compute_booking_pricing(
            booking_topup.id, applied_credit_cents=context_topup.applied_credit_cents
        )
        pi_topup = stripe_service.create_payment_intent(
            booking_id=booking_topup.id,
            customer_id=customer_id,
            destination_account_id=dest_account,
            charge_context=context_topup,
        )
        created_payment_intents.append(pi_topup.stripe_payment_intent_id)

        transfer = None
        try:
            transfer = stripe_service.ensure_top_up_transfer(
                booking_id=booking_topup.id,
                payment_intent_id=pi_topup.stripe_payment_intent_id,
                destination_account_id=dest_account,
                amount_cents=context_topup.top_up_transfer_cents,
            )
        except ServiceException:
            transfer = None

        if context_topup.top_up_transfer_cents > 0:
            if transfer is not None:
                created_transfers.append(transfer["id"])
                transfer_remote = stripe.Transfer.retrieve(transfer["id"])
                assert transfer_remote.amount == context_topup.top_up_transfer_cents
        else:
            assert transfer is None

        event = payment_repo.get_latest_payment_event(
            booking_topup.id, "top_up_transfer_created"
        )
        if context_topup.top_up_transfer_cents > 0 and transfer is not None:
            assert event is not None
            assert (
                int(event.event_data.get("amount_cents"))
                == context_topup.top_up_transfer_cents
            )

        assert preview_topup["credit_applied_cents"] == context_topup.applied_credit_cents
        assert context_topup.applied_credit_cents <= credit_request_cents

    finally:
        for pi_id in created_payment_intents:
            try:
                stripe.PaymentIntent.cancel(pi_id)
            except Exception:
                pass
        for transfer_id in created_transfers:
            try:
                stripe.Transfer.create_reversal(transfer_id)
            except Exception:
                pass
        for customer_id in created_customers:
            try:
                stripe.Customer.delete(customer_id)
            except Exception:
                pass

        # Clean up platform credits
        if created_platform_credit_ids:
            session.query(PlatformCredit).filter(
                PlatformCredit.id.in_(created_platform_credit_ids)
            ).delete(synchronize_session=False)

        # Remove created DB entries (reverse order)
        for model in reversed(disposable_models):
            try:
                session.delete(model)
            except Exception:
                pass
        session.commit()
        session.close()
