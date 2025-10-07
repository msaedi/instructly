import copy
import json

import pytest

from app.core.config import settings
from app.services.sender_registry import get_sender


@pytest.fixture(autouse=True)
def reset_sender_settings(monkeypatch):
    original_profiles = copy.deepcopy(getattr(settings, "_sender_profiles", {}))
    original_warning_flag = getattr(settings, "_sender_profiles_warning_logged", False)

    monkeypatch.setattr(settings, "email_sender_profiles_file", None, raising=False)
    monkeypatch.setattr(settings, "email_sender_profiles_json", None, raising=False)
    monkeypatch.setattr(settings, "_sender_profiles_warning_logged", False, raising=False)

    settings._sender_profiles = {}  # type: ignore[attr-defined]
    settings.refresh_sender_profiles("")

    yield

    settings._sender_profiles = original_profiles  # type: ignore[attr-defined]
    settings._sender_profiles_warning_logged = original_warning_flag  # type: ignore[attr-defined]
    settings.refresh_sender_profiles()


def test_get_sender_known_profile():
    settings.email_from_name = "Default Name"
    settings.email_from_address = "default@example.com"
    settings.email_reply_to = "reply-default@example.com"

    settings.refresh_sender_profiles(
        json.dumps(
            {
                "trust": {
                    "from_name": "InstaInstru Trust & Safety",
                    "from": "notifications@instainstru.com",
                    "reply_to": "support@instainstru.com",
                }
            }
        )
    )

    resolved = get_sender("trust")

    assert resolved["from_name"] == "InstaInstru Trust & Safety"
    assert resolved["from_address"] == "notifications@instainstru.com"
    assert resolved["reply_to"] == "support@instainstru.com"


def test_get_sender_falls_back_to_defaults_for_unknown_key():
    settings.email_from_name = "Default Name"
    settings.email_from_address = "default@example.com"
    settings.email_reply_to = "reply-default@example.com"

    settings.refresh_sender_profiles(
        json.dumps(
            {
                "trust": {
                    "from_name": "InstaInstru Trust",
                    "from": "trust@example.com",
                }
            }
        )
    )

    resolved = get_sender("unknown")

    assert resolved["from_name"] == "Default Name"
    assert resolved["from_address"] == "default@example.com"
    assert resolved["reply_to"] == "reply-default@example.com"


def test_partial_profile_inherits_reply_to_default():
    settings.email_from_name = "Default Name"
    settings.email_from_address = "default@example.com"
    settings.email_reply_to = "reply-default@example.com"

    settings.refresh_sender_profiles(
        json.dumps(
            {
                "trust": {
                    "from_name": "Trust",
                    "from": "trust@example.com",
                }
            }
        )
    )

    resolved = get_sender("trust")

    assert resolved["from_name"] == "Trust"
    assert resolved["from_address"] == "trust@example.com"
    assert resolved["reply_to"] == "reply-default@example.com"
