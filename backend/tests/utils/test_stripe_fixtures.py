from __future__ import annotations

import stripe
from stripe._stripe_object import StripeObject

from tests.utils.stripe_fixtures import (
    make_account,
    make_charge,
    make_event,
    make_list_object,
    make_payment_intent,
    make_refund,
    make_transfer,
    make_verification_session,
)


def _assert_real_stripe_object(obj: object, expected_cls: type[object]) -> None:
    assert isinstance(obj, expected_cls)
    assert isinstance(obj, StripeObject)
    assert type(obj) is not dict


def test_factories_return_correct_stripe_types() -> None:
    _assert_real_stripe_object(make_payment_intent(), stripe.PaymentIntent)
    _assert_real_stripe_object(make_charge(), stripe.Charge)
    _assert_real_stripe_object(make_transfer(), stripe.Transfer)
    _assert_real_stripe_object(make_refund(), stripe.Refund)
    _assert_real_stripe_object(make_account(), stripe.Account)
    _assert_real_stripe_object(
        make_event("payment_intent.succeeded", make_payment_intent()),
        stripe.Event,
    )
    _assert_real_stripe_object(make_list_object([make_verification_session()]), stripe.ListObject)
    _assert_real_stripe_object(
        make_verification_session(),
        stripe.identity.VerificationSession,
    )


def test_payment_intent_supports_attribute_and_bracket_access() -> None:
    payment_intent = make_payment_intent()

    _assert_real_stripe_object(payment_intent, stripe.PaymentIntent)
    assert payment_intent.id == "pi_test"
    assert payment_intent["id"] == "pi_test"


def test_payment_intent_overrides_work() -> None:
    payment_intent = make_payment_intent(amount=10000, metadata={"user_id": "test"})

    assert payment_intent.amount == 10000
    _assert_real_stripe_object(payment_intent.metadata, StripeObject)
    assert payment_intent.metadata["user_id"] == "test"


def test_account_settings_are_nested_stripe_objects() -> None:
    account = make_account()

    _assert_real_stripe_object(account.settings, StripeObject)
    _assert_real_stripe_object(account.requirements, StripeObject)
    assert account.settings["payouts"]["schedule"]["interval"] == "manual"


def test_payment_intent_latest_charge_is_real_charge() -> None:
    payment_intent = make_payment_intent(latest_charge=make_charge())

    _assert_real_stripe_object(payment_intent.latest_charge, stripe.Charge)
    assert payment_intent.latest_charge.transfer == "tr_test"


def test_payment_intent_omits_deprecated_charges_field() -> None:
    payment_intent = make_payment_intent()

    assert "charges" not in payment_intent


def test_event_and_list_object_convert_nested_resources() -> None:
    event = make_event("payment_intent.succeeded", make_payment_intent())
    list_object = make_list_object([make_verification_session()])

    _assert_real_stripe_object(event.data, StripeObject)
    _assert_real_stripe_object(event.data.object, stripe.PaymentIntent)
    assert isinstance(list_object.data, list)
    _assert_real_stripe_object(list_object.data[0], stripe.identity.VerificationSession)
