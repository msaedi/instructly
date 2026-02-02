from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import support


def _mock_scope(monkeypatch):
    def fake_request():
        class Dummy:
            scope = {"auth": {"method": "simple_token"}}

        return Dummy()

    monkeypatch.setattr(support, "get_http_request", fake_request)


class FakeClient:
    def __init__(self, *, user_payload=None, bookings_payload=None, recent_payload=None):
        self.user_payload = user_payload or {}
        self.bookings_payload = bookings_payload or {"bookings": [], "total_count": 0}
        self.recent_payload = recent_payload or {"bookings": []}

    async def lookup_user(self, identifier: str):
        return self.user_payload

    async def get_user_booking_history(self, user_id: str, limit: int = 10):
        return self.bookings_payload

    async def get_recent_bookings(self, limit: int = 20, hours: int = 24):
        return self.recent_payload


def test_safe_float_and_cents():
    assert support._safe_float("10.5") == 10.5
    assert support._safe_float("bad") is None
    assert support._cents_to_dollars(12345) == 123.45
    assert support._cents_to_dollars("bad") is None


def test_parse_time_and_duration():
    assert support._parse_time(None) is None
    assert support._parse_time(" ") is None
    assert support._parse_time("bad") is None
    assert support._parse_time("14:00").hour == 14
    assert support._parse_time("14:00:00").minute == 0

    assert support._duration_minutes("09:00", "10:30") == 90
    assert support._duration_minutes("23:30", "00:15") == 45
    assert support._duration_minutes(None, "10:00") is None


def test_derive_payment_status():
    assert support._derive_payment_status("completed") == "settled"
    assert support._derive_payment_status("cancelled") == "refunded"
    assert support._derive_payment_status("payment_failed") == "failed"
    assert support._derive_payment_status("pending") == "pending"
    assert support._derive_payment_status("other") is None


def test_format_booking_item_and_categorize():
    item = {
        "booking_id": "bk_1",
        "status": "confirmed",
        "booking_date": "2026-02-01",
        "start_time": "14:00",
        "end_time": "15:00",
        "instructor_name": "Sarah C.",
        "service_name": "Piano Lesson",
        "location_type": "student_location",
        "total_cents": 8000,
        "created_at": "2026-01-25T10:00:00Z",
    }
    formatted = support._format_booking_item(item)
    assert formatted["scheduled_at"] == "2026-02-01T14:00"
    assert formatted["duration_minutes"] == 60
    assert formatted["price"] == 80.0

    pending, issues = support._categorize_bookings(
        [formatted, {"status": "payment_failed", "id": "bk_2"}]
    )
    assert pending[0]["status"] == "confirmed"
    assert issues[0]["status"] == "payment_failed"

    no_schedule = support._format_booking_item({"booking_id": "bk_3"})
    assert no_schedule["scheduled_at"] is None


def test_messages_section():
    assert support._build_messages_section(False)["included"] is False
    included = support._build_messages_section(True)
    assert included["included"] is False
    assert included["note"] == "messages_not_available"


def test_account_flags_and_support_notes():
    user = {
        "is_verified": False,
        "instructor_status": "suspended",
        "total_bookings": 12,
        "total_spent_cents": 12300,
    }
    booking_issues = [
        {"status": "payment_failed"},
        {"status": "dispute_open"},
    ]
    flags = support._derive_account_flags(user, booking_issues)
    assert flags["has_issues"] is True
    assert "unverified_email" in flags["issues"]
    assert "failed_payment" in flags["issues"]

    notes = support._build_support_notes(user, [{"id": "bk"}], booking_issues)
    assert any("Loyal customer" in action for action in notes["quick_actions"])
    assert any("Booking issue" in warning for warning in notes["warnings"])


def test_build_user_profile_and_payments():
    user = {
        "user_id": "u1",
        "email": "john@example.com",
        "phone": "+1234567890",
        "name": "John",
        "role": "student",
        "created_at": "2026-01-01T00:00:00Z",
        "is_verified": True,
        "stripe_customer_id": "cus_123",
    }
    profile = support._build_user_profile(user)
    assert profile["email"] == "john@example.com"
    assert profile["stripe_customer_id"] == "cus_123"

    bookings = [
        {"id": "bk1", "status": "completed", "price": 100.0, "created_at": "x"},
        {"id": "bk2", "status": "payment_failed", "price": 50.0, "created_at": "y"},
        {"id": "bk3", "status": "dispute_open", "price": 80.0, "created_at": "z"},
    ]
    payments = support._build_payments_section(bookings, True)
    assert len(payments["recent_charges"]) >= 1
    assert len(payments["failed_charges"]) == 1
    assert len(payments["disputes"]) == 1

    assert support._build_payments_section(bookings, False)["included"] is False


def test_require_scope_variants(monkeypatch):
    def fake_request_jwt():
        class Dummy:
            scope = {"auth": {"method": "jwt", "claims": {}}}

        return Dummy()

    monkeypatch.setattr(support, "get_http_request", fake_request_jwt)
    support._require_scope("mcp:read")

    def fake_request_none():
        class Dummy:
            scope = {"auth": {"method": "oauth", "claims": {}}}

        return Dummy()

    monkeypatch.setattr(support, "get_http_request", fake_request_none)
    with pytest.raises(PermissionError):
        support._require_scope("mcp:write")


@pytest.mark.asyncio
async def test_support_lookup_by_email(monkeypatch):
    _mock_scope(monkeypatch)
    user_payload = {
        "found": True,
        "user": {
            "user_id": "u1",
            "email": "john@example.com",
            "phone": "+1234567890",
            "name": "John Smith",
            "role": "student",
            "created_at": "2025-06-15T00:00:00Z",
            "is_verified": True,
            "total_bookings": 15,
            "total_spent_cents": 25000,
            "stripe_customer_id": "cus_123",
        },
    }
    bookings_payload = {
        "bookings": [
            {
                "booking_id": "bk_1",
                "status": "completed",
                "booking_date": "2026-01-28",
                "start_time": "14:00",
                "end_time": "15:00",
                "instructor_name": "Sarah C.",
                "service_name": "Piano Lesson",
                "location_type": "student_location",
                "total_cents": 8000,
                "created_at": "2026-01-25T10:00:00Z",
            }
        ],
        "total_count": 1,
    }

    mcp = FastMCP("test")
    tools = support.register_tools(
        mcp,
        FakeClient(user_payload=user_payload, bookings_payload=bookings_payload),
    )

    result = await tools["instainstru_support_lookup"]("john@example.com", "email")

    assert result["user"]["email"] == "john@example.com"
    assert result["bookings"]["returned_count"] == 1
    assert result["payments"].get("included") is None


@pytest.mark.asyncio
async def test_support_lookup_user_not_found(monkeypatch):
    _mock_scope(monkeypatch)
    user_payload = {"found": False, "user": None}

    mcp = FastMCP("test")
    tools = support.register_tools(mcp, FakeClient(user_payload=user_payload))

    result = await tools["instainstru_support_lookup"]("missing@example.com", "email")

    assert "error" in result
    assert "No user found" in result["error"]


@pytest.mark.asyncio
async def test_support_lookup_by_booking_id(monkeypatch):
    _mock_scope(monkeypatch)
    recent_payload = {
        "bookings": [
            {
                "booking_id": "bk_2",
                "status": "confirmed",
                "booking_date": "2026-01-28",
                "start_time": "14:00",
                "end_time": "15:00",
                "student_name": "John S.",
                "instructor_name": "Sarah C.",
                "service_name": "Guitar Lesson",
                "category": "Music",
                "location_type": "student_location",
                "total_cents": 9000,
                "created_at": "2026-01-25T10:00:00Z",
            }
        ]
    }

    mcp = FastMCP("test")
    tools = support.register_tools(mcp, FakeClient(recent_payload=recent_payload))

    result = await tools["instainstru_support_lookup"]("bk_2", "booking_id")

    assert result["booking"]["id"] == "bk_2"
    assert result["student"]["name"] == "John S."


@pytest.mark.asyncio
async def test_support_lookup_booking_not_found(monkeypatch):
    _mock_scope(monkeypatch)
    recent_payload = {"bookings": []}

    mcp = FastMCP("test")
    tools = support.register_tools(mcp, FakeClient(recent_payload=recent_payload))

    result = await tools["instainstru_support_lookup"]("bk_404", "booking_id")

    assert "error" in result
    assert "Booking not found" in result["error"]


@pytest.mark.asyncio
async def test_support_lookup_includes_messages_when_requested(monkeypatch):
    _mock_scope(monkeypatch)
    user_payload = {
        "found": True,
        "user": {
            "user_id": "u1",
            "email": "john@example.com",
            "name": "John",
            "role": "student",
            "created_at": "2025-06-15T00:00:00Z",
            "is_verified": True,
            "total_bookings": 1,
            "total_spent_cents": 1000,
        },
    }

    mcp = FastMCP("test")
    tools = support.register_tools(mcp, FakeClient(user_payload=user_payload))

    result = await tools["instainstru_support_lookup"](
        "john@example.com",
        "email",
        include_messages=True,
        include_payment_history=False,
    )

    assert result["messages"]["included"] is False
    assert result["payments"]["included"] is False


@pytest.mark.asyncio
async def test_support_lookup_handles_booking_history_error(monkeypatch):
    _mock_scope(monkeypatch)

    class ErrorClient(FakeClient):
        async def get_user_booking_history(self, user_id: str, limit: int = 10):
            raise RuntimeError("boom")

    user_payload = {
        "found": True,
        "user": {
            "user_id": "u1",
            "email": "john@example.com",
            "name": "John",
            "role": "student",
            "created_at": "2025-06-15T00:00:00Z",
            "is_verified": True,
            "total_bookings": 0,
            "total_spent_cents": 0,
        },
    }

    mcp = FastMCP("test")
    tools = support.register_tools(mcp, ErrorClient(user_payload=user_payload))

    result = await tools["instainstru_support_lookup"]("john@example.com", "email")

    assert result["bookings"]["total_count"] == 0
