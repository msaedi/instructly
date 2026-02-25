"""Coverage tests for pricing routes — DomainException → to_http_exception() on L38."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.core.exceptions import ValidationException
from app.routes.v1 import pricing as routes


class _FailingPricingService:
    def compute_quote_pricing(self, **_kwargs):
        raise ValidationException("Invalid pricing input", code="invalid_input")


class _SuccessPricingService:
    def compute_quote_pricing(self, **_kwargs):
        return {
            "base_price_cents": 5000,
            "student_fee_cents": 350,
            "instructor_platform_fee_cents": 500,
            "target_instructor_payout_cents": 4500,
            "credit_applied_cents": 0,
            "student_pay_cents": 5350,
            "application_fee_cents": 850,
            "top_up_transfer_cents": 0,
            "instructor_tier_pct": 0.10,
            "line_items": [],
        }


# ---- L35-36: DomainException → to_http_exception() ----
def test_preview_pricing_domain_exception():
    payload = SimpleNamespace(
        instructor_id="instr-1",
        service_id="svc-1",
        slots=[],
    )
    with pytest.raises(HTTPException) as exc:
        routes.preview_selection_pricing(
            payload=payload,
            current_user=SimpleNamespace(id="user-1"),
            pricing_service=_FailingPricingService(),
        )
    assert exc.value.status_code == 400


# ---- Success path ----
def test_preview_pricing_success():
    payload = SimpleNamespace(
        instructor_id="instr-1",
        service_id="svc-1",
        slots=[],
    )
    result = routes.preview_selection_pricing(
        payload=payload,
        current_user=SimpleNamespace(id="user-1"),
        pricing_service=_SuccessPricingService(),
    )
    assert result.student_pay_cents == 5350
