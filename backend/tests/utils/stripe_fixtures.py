from __future__ import annotations

from typing import Any, TypeVar

import stripe

_FIXTURE_API_KEY = "sk_test_fixture"

StripeObjectT = TypeVar("StripeObjectT", bound=stripe.StripeObject)


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(overrides)
    return merged


def _normalize_payload(value: Any) -> Any:
    if isinstance(value, stripe.StripeObject):
        raw = value.to_dict()
        return {key: _normalize_payload(item) for key, item in raw.items()}
    if isinstance(value, dict):
        return {key: _normalize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_payload(item) for item in value]
    return value


def _construct(cls: type[StripeObjectT], payload: dict[str, Any]) -> StripeObjectT:
    return cls.construct_from(_normalize_payload(payload), _FIXTURE_API_KEY)


def _assert_constructed(obj: Any, expected_cls: type[StripeObjectT]) -> None:
    if not isinstance(obj, expected_cls):
        raise TypeError(f"Expected {expected_cls.__name__}, got {type(obj).__name__}")
    if type(obj) is dict:
        raise TypeError("Expected constructed Stripe resource, got plain dict")


def make_payment_intent(**overrides: Any) -> stripe.PaymentIntent:
    if "charges" in overrides:
        raise ValueError("make_payment_intent intentionally does not support deprecated 'charges'")
    payload = _merge(
        {
            "id": "pi_test",
            "object": "payment_intent",
            "amount": 5000,
            "amount_received": 5000,
            "currency": "usd",
            "status": "succeeded",
            "metadata": {},
        },
        overrides,
    )
    payment_intent = _construct(stripe.PaymentIntent, payload)
    _assert_constructed(payment_intent, stripe.PaymentIntent)
    return payment_intent


def make_charge(**overrides: Any) -> stripe.Charge:
    payload = _merge(
        {
            "id": "ch_test",
            "object": "charge",
            "amount": 5000,
            "currency": "usd",
            "status": "succeeded",
            "payment_intent": "pi_test",
            "transfer": "tr_test",
            "metadata": {},
        },
        overrides,
    )
    charge = _construct(stripe.Charge, payload)
    _assert_constructed(charge, stripe.Charge)
    return charge


def make_transfer(**overrides: Any) -> stripe.Transfer:
    payload = _merge(
        {
            "id": "tr_test",
            "object": "transfer",
            "amount": 4000,
            "currency": "usd",
            "destination": "acct_test",
            "source_transaction": "ch_test",
            "metadata": {},
        },
        overrides,
    )
    transfer = _construct(stripe.Transfer, payload)
    _assert_constructed(transfer, stripe.Transfer)
    return transfer


def make_payout(**overrides: Any) -> stripe.Payout:
    payload = _merge(
        {
            "id": "po_test",
            "object": "payout",
            "amount": 5000,
            "currency": "usd",
            "status": "paid",
        },
        overrides,
    )
    payout = _construct(stripe.Payout, payload)
    _assert_constructed(payout, stripe.Payout)
    return payout


def make_login_link(**overrides: Any) -> stripe.LoginLink:
    payload = _merge(
        {
            "object": "login_link",
            "created": 1_700_000_000,
            "url": "https://stripe.test/dashboard",
        },
        overrides,
    )
    login_link = _construct(stripe.LoginLink, payload)
    _assert_constructed(login_link, stripe.LoginLink)
    return login_link


def make_refund(**overrides: Any) -> stripe.Refund:
    payload = _merge(
        {
            "id": "re_test",
            "object": "refund",
            "amount": 5000,
            "currency": "usd",
            "status": "succeeded",
            "charge": "ch_test",
        },
        overrides,
    )
    refund = _construct(stripe.Refund, payload)
    _assert_constructed(refund, stripe.Refund)
    return refund


def make_account(**overrides: Any) -> stripe.Account:
    payload = _merge(
        {
            "id": "acct_test",
            "object": "account",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
            "requirements": {"currently_due": [], "past_due": []},
            "settings": {"payouts": {"schedule": {"interval": "manual"}}},
        },
        overrides,
    )
    account = _construct(stripe.Account, payload)
    _assert_constructed(account, stripe.Account)
    if payload.get("settings") is not None:
        _assert_constructed(account.settings, stripe.StripeObject)
    return account


def make_event(
    event_type: str, data_object: dict[str, Any] | stripe.StripeObject, **overrides: Any
) -> stripe.Event:
    payload = _merge(
        {
            "id": "evt_test",
            "object": "event",
            "type": event_type,
            "data": {"object": data_object},
            "api_version": "2026-03-25.dahlia",
        },
        overrides,
    )
    event = _construct(stripe.Event, payload)
    _assert_constructed(event, stripe.Event)
    return event


def make_list_object(data: list[Any], **overrides: Any) -> stripe.ListObject:
    payload = _merge(
        {
            "object": "list",
            "data": data,
            "has_more": False,
            "url": "/v1/test",
        },
        overrides,
    )
    list_object = _construct(stripe.ListObject, payload)
    _assert_constructed(list_object, stripe.ListObject)
    return list_object


def make_verification_session(**overrides: Any) -> stripe.identity.VerificationSession:
    payload = _merge(
        {
            "id": "vs_test",
            "object": "identity.verification_session",
            "status": "verified",
        },
        overrides,
    )
    verification_session = _construct(stripe.identity.VerificationSession, payload)
    _assert_constructed(verification_session, stripe.identity.VerificationSession)
    return verification_session


__all__ = [
    "make_account",
    "make_charge",
    "make_event",
    "make_login_link",
    "make_list_object",
    "make_payment_intent",
    "make_payout",
    "make_refund",
    "make_transfer",
    "make_verification_session",
]
