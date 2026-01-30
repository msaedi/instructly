"""Tests for Sentry integration."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

from instainstru_mcp.config import Settings
from instainstru_mcp.server import _init_sentry, get_git_sha


def test_get_git_sha_returns_sha_on_success():
    with patch("instainstru_mcp.server.subprocess.check_output") as mock_output:
        mock_output.return_value = "abc123\n"
        result = get_git_sha()

    assert result == "abc123"
    mock_output.assert_called_once_with(
        ["git", "rev-parse", "--short", "HEAD"],
        stderr=subprocess.DEVNULL,
        text=True,
    )


def test_get_git_sha_returns_unknown_on_exception():
    with patch("instainstru_mcp.server.subprocess.check_output") as mock_output:
        mock_output.side_effect = Exception("git not available")
        result = get_git_sha()

    assert result == "unknown"


def test_get_git_sha_returns_unknown_on_called_process_error():
    with patch("instainstru_mcp.server.subprocess.check_output") as mock_output:
        mock_output.side_effect = subprocess.CalledProcessError(1, "git")
        result = get_git_sha()

    assert result == "unknown"


def test_init_sentry_skips_without_dsn():
    settings = Settings(_env_file=None, sentry_dsn=None)
    with patch("instainstru_mcp.server.sentry_sdk.init") as mock_init:
        with patch("instainstru_mcp.server.get_git_sha") as mock_sha:
            _init_sentry(settings)

    mock_init.assert_not_called()
    mock_sha.assert_not_called()


def test_init_sentry_initializes_with_dsn():
    settings = Settings(
        _env_file=None,
        sentry_dsn="https://test@sentry.io/123",
        environment="test",
    )

    with patch("instainstru_mcp.server.sentry_sdk.init") as mock_init:
        with patch("instainstru_mcp.server.get_git_sha", return_value="abc123"):
            _init_sentry(settings)

    assert mock_init.call_count == 1
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://test@sentry.io/123"
    assert kwargs["environment"] == "test"
    assert kwargs["release"] == "abc123"
    assert kwargs["send_default_pii"] is True
    assert kwargs["traces_sample_rate"] == 0.1
    assert kwargs["profiles_sample_rate"] == 0.1

    integrations = kwargs["integrations"]
    assert len(integrations) == 1
    from sentry_sdk.integrations.mcp import MCPIntegration

    assert isinstance(integrations[0], MCPIntegration)


def test_settings_defaults_for_sentry():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.sentry_dsn is None
    assert settings.environment == "development"
