from __future__ import annotations

from datetime import datetime, timezone

from app.services.mcp_invite_service import MCPInviteService


def test_mcp_invite_service_empty_email_lookup(db):
    service = MCPInviteService(db)
    assert service.get_existing_users([]) == []


def test_mcp_invite_service_invalid_cap_falls_back(db, monkeypatch):
    service = MCPInviteService(db)

    def _bad_config():
        return ({"founding_instructor_cap": "not-a-number"}, datetime.now(timezone.utc))

    monkeypatch.setattr(service._config_service, "get_pricing_config", _bad_config)
    monkeypatch.setattr(service._profile_repo, "count_founding_instructors", lambda: 0)

    assert service.get_founding_cap_remaining() == 100


def test_mcp_invite_service_detail_missing_returns_empty(db):
    service = MCPInviteService(db)
    assert service.get_invite_detail("missing-id") == {}
