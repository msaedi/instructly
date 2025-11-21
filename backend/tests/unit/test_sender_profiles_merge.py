import json

import pytest

from app.core.config import settings
from app.services.sender_registry import get_sender


@pytest.fixture(autouse=True)
def reset_sender_profiles(monkeypatch):
    original_profiles = getattr(settings, "_sender_profiles", {}).copy()
    original_warning_flag = getattr(settings, "_sender_profiles_warning_logged", False)
    original_file = settings.email_sender_profiles_file
    original_json = settings.email_sender_profiles_json

    monkeypatch.setattr(settings, "email_sender_profiles_file", None, raising=False)
    monkeypatch.setattr(settings, "email_sender_profiles_json", None, raising=False)
    monkeypatch.setattr(settings, "_sender_profiles_warning_logged", False, raising=False)

    settings._sender_profiles = {}  # type: ignore[attr-defined]
    settings.refresh_sender_profiles("")

    yield

    settings._sender_profiles = original_profiles  # type: ignore[attr-defined]
    settings._sender_profiles_warning_logged = original_warning_flag  # type: ignore[attr-defined]
    monkeypatch.setattr(settings, "email_sender_profiles_file", original_file, raising=False)
    monkeypatch.setattr(settings, "email_sender_profiles_json", original_json, raising=False)
    settings.refresh_sender_profiles()


def test_file_profiles_overridden_by_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "email_from_name", "Default Name", raising=False)
    monkeypatch.setattr(settings, "email_from_address", "default@example.com", raising=False)
    monkeypatch.setattr(settings, "email_reply_to", "reply-default@example.com", raising=False)

    file_payload = {
        "bookings": {
            "from_name": "iNSTAiNSTRU Bookings",
            "from": "bookings@instainstru.com",
            "reply_to": "support@instainstru.com",
        },
        "payments": {
            "from_name": "iNSTAiNSTRU Billing",
            "from": "billing@instainstru.com",
            "reply_to": "billing@instainstru.com",
        },
    }
    file_path = tmp_path / "profiles.json"
    file_path.write_text(json.dumps(file_payload), encoding="utf-8")

    monkeypatch.setattr(settings, "email_sender_profiles_file", str(file_path), raising=False)
    settings.refresh_sender_profiles("")

    env_override = json.dumps({"payments": {"reply_to": "accounts-payable@instainstru.com"}})
    settings.refresh_sender_profiles(env_override)

    payments_profile = get_sender("payments")
    assert payments_profile["from_name"] == "iNSTAiNSTRU Billing"
    assert payments_profile["from_address"] == "billing@instainstru.com"
    assert payments_profile["reply_to"] == "accounts-payable@instainstru.com"

    bookings_profile = get_sender("bookings")
    assert bookings_profile["from_name"] == "iNSTAiNSTRU Bookings"
    assert bookings_profile["from_address"] == "bookings@instainstru.com"
    assert bookings_profile["reply_to"] == "support@instainstru.com"

    fallback_profile = get_sender("unknown")
    assert fallback_profile["from_name"] == "Default Name"
    assert fallback_profile["from_address"] == "default@example.com"
    assert fallback_profile["reply_to"] == "reply-default@example.com"
