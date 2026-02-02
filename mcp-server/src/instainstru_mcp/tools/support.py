"""
Support Cockpit - Quick user/booking lookup for customer support.

Aggregates user info, bookings, payments, and messages into one view.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from ..client import InstaInstruClient

BookingIdentifier = Literal["email", "phone", "user_id", "booking_id"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_scope(required_scope: str) -> None:
    request = get_http_request()
    auth = getattr(request, "scope", {}).get("auth", {})
    method = auth.get("method") if isinstance(auth, dict) else None
    if method == "simple_token":
        return
    claims = auth.get("claims", {}) if isinstance(auth, dict) else {}
    scope_value = ""
    if isinstance(claims, dict):
        scope_value = claims.get("scope") or claims.get("scp") or ""
    if not scope_value and isinstance(auth, dict):
        scope_value = auth.get("scope") or ""
    scopes = {scope for scope in scope_value.split() if scope}
    if required_scope not in scopes:
        if required_scope == "mcp:read" and method in {"jwt", "workos"}:
            return
        raise PermissionError(f"Missing required scope: {required_scope}")


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cents_to_dollars(value: Any) -> float | None:
    cents = _safe_float(value)
    if cents is None:
        return None
    return round(cents / 100.0, 2)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    token = value.strip()
    if not token:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(token, fmt)
        except ValueError:
            continue
    return None


def _duration_minutes(start_time: str | None, end_time: str | None) -> int | None:
    start = _parse_time(start_time)
    end = _parse_time(end_time)
    if not start or not end:
        return None
    delta = (end - start).total_seconds() / 60.0
    if delta < 0:
        delta += 24 * 60
    return int(delta)


def _format_booking_item(item: dict[str, Any]) -> dict[str, Any]:
    booking_date = item.get("booking_date")
    start_time = item.get("start_time")
    scheduled_at = None
    if booking_date and start_time:
        scheduled_at = f"{booking_date}T{start_time}"

    return {
        "id": item.get("booking_id") or item.get("id"),
        "status": item.get("status"),
        "instructor_name": item.get("instructor_name"),
        "service": item.get("service_name") or item.get("service"),
        "scheduled_at": scheduled_at,
        "duration_minutes": _duration_minutes(start_time, item.get("end_time")),
        "location_type": item.get("location_type"),
        "price": _cents_to_dollars(item.get("total_cents")),
        "platform_fee": None,
        "payment_status": _derive_payment_status(item.get("status")),
        "created_at": item.get("created_at"),
    }


def _derive_payment_status(status: str | None) -> str | None:
    if not status:
        return None
    key = str(status).lower()
    if "complete" in key:
        return "settled"
    if "cancel" in key or "refund" in key:
        return "refunded"
    if "fail" in key:
        return "failed"
    if "pending" in key or "confirm" in key:
        return "pending"
    return None


def _categorize_bookings(
    bookings: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for booking in bookings:
        status = (booking.get("status") or "").lower()
        if status in {"confirmed", "pending", "scheduled"}:
            pending.append(booking)
        if any(token in status for token in ("fail", "dispute", "cancel", "no-show")):
            issues.append(booking)
    return pending, issues


def _build_messages_section(include_messages: bool) -> dict[str, Any]:
    if not include_messages:
        return {
            "included": False,
            "active_threads": None,
            "unread_count": None,
        }
    return {
        "included": False,
        "active_threads": None,
        "unread_count": None,
        "note": "messages_not_available",
    }


def _derive_account_flags(
    user: dict[str, Any], booking_issues: list[dict[str, Any]]
) -> dict[str, Any]:
    issues: list[str] = []
    if user and not user.get("is_verified", True):
        issues.append("unverified_email")
    if user and user.get("instructor_status") in {"suspended", "blocked", "inactive"}:
        issues.append("instructor_restricted")
    if any("failed" in (b.get("status") or "").lower() for b in booking_issues):
        issues.append("failed_payment")
    if any("dispute" in (b.get("status") or "").lower() for b in booking_issues):
        issues.append("disputed_charge")

    return {
        "has_issues": bool(issues),
        "issues": issues,
    }


def _build_support_notes(
    user: dict[str, Any],
    bookings: list[dict[str, Any]],
    booking_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    quick_actions: list[str] = []
    warnings: list[str] = []

    total_bookings = user.get("total_bookings") if user else None
    if isinstance(total_bookings, int) and total_bookings >= 10:
        quick_actions.append(f"Loyal customer: {total_bookings} bookings")

    total_spent = user.get("total_spent_cents") if user else None
    total_spent_dollars = _cents_to_dollars(total_spent)
    if total_spent_dollars is not None:
        quick_actions.append(f"Total spend: ${total_spent_dollars:.2f}")

    if bookings:
        quick_actions.append(f"Recent bookings: {len(bookings)}")

    for issue in booking_issues:
        status = issue.get("status")
        if status:
            warnings.append(f"Booking issue: {status}")

    return {"quick_actions": quick_actions, "warnings": warnings}


def _build_user_profile(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("user_id"),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "name": user.get("name"),
        "role": user.get("role"),
        "created_at": user.get("created_at"),
        "status": "active",
        "email_verified": user.get("is_verified"),
        "phone_verified": None,
        "has_2fa": None,
        "stripe_customer_id": user.get("stripe_customer_id"),
        "platform_credit_balance": None,
        "referral_code": None,
    }


def _build_payments_section(
    bookings: list[dict[str, Any]], include_payment_history: bool
) -> dict[str, Any]:
    if not include_payment_history:
        return {"included": False}

    recent_charges: list[dict[str, Any]] = []
    failed_charges: list[dict[str, Any]] = []
    disputes: list[dict[str, Any]] = []

    for booking in bookings:
        status = (booking.get("status") or "").lower()
        charge = {
            "booking_id": booking.get("id"),
            "amount": booking.get("price"),
            "status": "succeeded" if status == "completed" else status,
            "created_at": booking.get("created_at"),
        }
        if "fail" in status:
            failed_charges.append(charge)
        elif "dispute" in status:
            disputes.append(charge)
        elif status:
            recent_charges.append(charge)

    return {
        "default_payment_method": None,
        "recent_charges": recent_charges,
        "failed_charges": failed_charges,
        "disputes": disputes,
    }


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def _lookup_user(identifier: str) -> dict[str, Any] | None:
        result = await client.lookup_user(identifier)
        if result.get("found") is False:
            return None
        return result.get("user")

    async def _fetch_user_bookings(user_id: str, limit: int) -> dict[str, Any]:
        return await client.get_user_booking_history(user_id=user_id, limit=limit)

    async def _lookup_booking_recent(booking_id: str, limit: int) -> dict[str, Any] | None:
        recent = await client.get_recent_bookings(limit=limit, hours=168)
        for item in recent.get("bookings", []):
            if item.get("booking_id") == booking_id:
                return item
        return None

    async def instainstru_support_lookup(
        identifier: str,
        identifier_type: BookingIdentifier = "email",
        include_messages: bool = False,
        include_payment_history: bool = True,
        booking_limit: int = 10,
    ) -> dict:
        """
        Look up a user or booking for customer support.

        Gathers:
        - User profile and account status
        - Recent bookings with payment status
        - Any active issues (failed payments, disputes)
        - Recent messages (if requested)
        - Instructor info (if looking up instructor)

        Args:
            identifier: Email, phone, user ID, or booking ID to look up
            identifier_type: Type of identifier provided
            include_messages: Include recent message threads (slower)
            include_payment_history: Include detailed payment history
            booking_limit: Max bookings to return

        Returns:
            Comprehensive support view for the user/booking
        """
        _require_scope("mcp:read")

        id_type = identifier_type or "email"
        id_value = identifier.strip()
        booking_limit = max(1, min(int(booking_limit or 10), 50))
        generated_at = _utc_now().isoformat()

        if id_type == "booking_id":
            booking = await _lookup_booking_recent(id_value, limit=booking_limit)
            if not booking:
                return {
                    "meta": {
                        "generated_at": generated_at,
                        "lookup_type": id_type,
                        "identifier": id_value,
                    },
                    "error": "Booking not found in recent history",
                    "suggestions": [
                        "Confirm the booking ID",
                        "Try again later or search by user",
                    ],
                }

            formatted = _format_booking_item(booking)
            notes = {
                "quick_actions": ["Booking located in recent history"],
                "warnings": [],
            }
            return {
                "meta": {
                    "generated_at": generated_at,
                    "lookup_type": id_type,
                    "identifier": id_value,
                },
                "booking": {
                    "id": formatted.get("id"),
                    "status": formatted.get("status"),
                    "created_at": formatted.get("created_at"),
                    "scheduled_at": formatted.get("scheduled_at"),
                    "completed_at": None,
                    "duration_minutes": formatted.get("duration_minutes"),
                    "location_type": formatted.get("location_type"),
                    "location_address": None,
                    "service": {
                        "name": formatted.get("service"),
                        "category": booking.get("category"),
                    },
                    "pricing": {
                        "base_price": formatted.get("price"),
                        "platform_fee": formatted.get("platform_fee"),
                        "credits_applied": None,
                        "total_charged": formatted.get("price"),
                        "instructor_payout": None,
                    },
                    "payment": {
                        "status": formatted.get("payment_status"),
                        "stripe_payment_intent": None,
                        "authorized_at": None,
                        "captured_at": None,
                        "settled_at": None,
                    },
                    "cancellation": None,
                    "review": None,
                },
                "student": {
                    "id": None,
                    "name": booking.get("student_name"),
                    "email": None,
                    "phone": None,
                },
                "instructor": {
                    "id": None,
                    "name": booking.get("instructor_name"),
                    "email": None,
                    "phone": None,
                },
                "timeline": [
                    {"event": "created", "at": formatted.get("created_at")},
                ],
                "messages": _build_messages_section(include_messages),
                "support_notes": notes,
            }

        user = await _lookup_user(id_value)
        if not user:
            return {
                "meta": {
                    "generated_at": generated_at,
                    "lookup_type": id_type,
                    "identifier": id_value,
                },
                "error": f"No user found with {id_type}={id_value}",
                "suggestions": ["Check spelling", "Try different identifier type"],
            }

        bookings_task = _fetch_user_bookings(user["user_id"], booking_limit)
        results = await asyncio.gather(
            bookings_task,
            return_exceptions=True,
        )
        bookings_payload_raw = results[0]
        if isinstance(bookings_payload_raw, BaseException):
            bookings_payload: dict[str, Any] = {
                "bookings": [],
                "total_count": 0,
            }
        else:
            bookings_payload = bookings_payload_raw

        raw_bookings = bookings_payload.get("bookings", [])
        formatted_bookings = [_format_booking_item(item) for item in raw_bookings]
        pending, issues = _categorize_bookings(formatted_bookings)

        account_flags = _derive_account_flags(user, issues)
        support_notes = _build_support_notes(user, formatted_bookings, issues)

        payments = _build_payments_section(formatted_bookings, include_payment_history)
        messages = _build_messages_section(include_messages)

        return {
            "meta": {
                "generated_at": generated_at,
                "lookup_type": id_type,
                "identifier": id_value,
            },
            "user": _build_user_profile(user),
            "account_flags": account_flags,
            "bookings": {
                "total_count": bookings_payload.get("total_count") or len(raw_bookings),
                "returned_count": len(formatted_bookings),
                "recent": formatted_bookings,
                "pending": pending,
                "issues": issues,
            },
            "payments": payments,
            "messages": messages,
            "support_notes": support_notes,
        }

    mcp.tool()(instainstru_support_lookup)
    return {"instainstru_support_lookup": instainstru_support_lookup}


__all__ = [
    "register_tools",
    "_build_support_notes",
    "_derive_account_flags",
    "_build_messages_section",
    "_build_payments_section",
    "_format_booking_item",
    "_duration_minutes",
    "_parse_time",
    "_cents_to_dollars",
    "_safe_float",
]
