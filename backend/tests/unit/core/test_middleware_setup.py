"""Unit tests for core/middleware_setup.py — middleware registration and helpers."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.core.middleware_setup as middleware_module
from app.core.middleware_setup import (
    EnsureCorsOnErrorMiddleware,
    SSEAwareGZipMiddleware,
    _compute_allowed_origins,
    _log_bgc_config_summary,
    _resolve_origin_regex,
    add_site_headers,
    attach_identity,
    register_middleware,
)

# ---------------------------------------------------------------------------
# add_site_headers
# ---------------------------------------------------------------------------


class TestAddSiteHeaders:
    @pytest.mark.asyncio
    async def test_sets_headers(self) -> None:
        request = MagicMock()
        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)

        with patch.dict(os.environ, {"SITE_MODE": "beta"}):
            result = await add_site_headers(request, call_next)

        assert result.headers["X-Site-Mode"] == "beta"
        assert "X-Phase" in result.headers

    @pytest.mark.asyncio
    async def test_exception_caught(self) -> None:
        request = MagicMock()
        response = MagicMock()
        response.headers = property(lambda self: (_ for _ in ()).throw(Exception("boom")))
        call_next = AsyncMock(return_value=response)

        result = await add_site_headers(request, call_next)
        assert result is response


# ---------------------------------------------------------------------------
# attach_identity
# ---------------------------------------------------------------------------


class TestAttachIdentity:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        request = MagicMock()
        request.state = MagicMock()
        call_next = AsyncMock(return_value=MagicMock())

        with patch("app.core.middleware_setup.resolve_identity", return_value="user:123"):
            await attach_identity(request, call_next)

        assert request.state.rate_identity == "user:123"

    @pytest.mark.asyncio
    async def test_exception_falls_back(self) -> None:
        request = MagicMock()
        request.state = MagicMock()
        call_next = AsyncMock(return_value=MagicMock())

        with patch("app.core.middleware_setup.resolve_identity", side_effect=Exception("fail")):
            await attach_identity(request, call_next)

        assert request.state.rate_identity == "ip:unknown"


# ---------------------------------------------------------------------------
# _compute_allowed_origins
# ---------------------------------------------------------------------------


class TestComputeAllowedOrigins:
    @patch("app.core.middleware_setup.settings")
    def test_preview_mode(self, mock_settings: MagicMock) -> None:
        mock_settings.preview_frontend_domain = "preview.example.com"
        with patch.dict(os.environ, {"SITE_MODE": "preview", "CORS_ALLOW_ORIGINS": "https://extra.com"}):
            origins = _compute_allowed_origins()
        assert "https://preview.example.com" in origins
        assert "https://extra.com" in origins

    @patch("app.core.middleware_setup.settings")
    def test_prod_mode(self, mock_settings: MagicMock) -> None:
        mock_settings.prod_frontend_origins_csv = "https://app.example.com, https://www.example.com"
        with patch.dict(os.environ, {"SITE_MODE": "prod"}):
            origins = _compute_allowed_origins()
        assert "https://app.example.com" in origins

    @patch("app.core.middleware_setup.settings")
    def test_prod_mode_empty_csv_defaults(self, mock_settings: MagicMock) -> None:
        mock_settings.prod_frontend_origins_csv = ""
        with patch.dict(os.environ, {"SITE_MODE": "beta"}):
            origins = _compute_allowed_origins()
        assert "https://app.instainstru.com" in origins

    def test_dev_mode_with_extra(self) -> None:
        with patch.dict(os.environ, {"SITE_MODE": "local", "CORS_ALLOW_ORIGINS": "http://custom.dev"}):
            origins = _compute_allowed_origins()
        assert "http://custom.dev" in origins


# ---------------------------------------------------------------------------
# _log_bgc_config_summary
# ---------------------------------------------------------------------------


class TestLogBgcConfigSummary:
    def test_logs_once_and_skips_second_call(self) -> None:
        middleware_module._BGC_ENV_LOGGED = False
        with patch("app.core.middleware_setup.settings") as mock_settings:
            mock_settings.checkr_api_key = None
            mock_settings.site_mode = "local"
            mock_settings.checkr_env = "sandbox"
            mock_settings.checkr_api_base = ""
            mock_settings.checkr_hosted_workflow = None
            mock_settings.checkr_package = None
            mock_settings.checkr_default_package = None

            _log_bgc_config_summary(["http://localhost:3000"])
            assert middleware_module._BGC_ENV_LOGGED is True

            # Second call should be a no-op
            _log_bgc_config_summary(["http://localhost:3000"])

        middleware_module._BGC_ENV_LOGGED = False  # cleanup


# ---------------------------------------------------------------------------
# _resolve_origin_regex
# ---------------------------------------------------------------------------


class TestResolveOriginRegex:
    def test_prod_mode_returns_none(self) -> None:
        with patch.dict(os.environ, {"SITE_MODE": "prod"}):
            assert _resolve_origin_regex() is None

    def test_dev_mode_returns_regex(self) -> None:
        with patch.dict(os.environ, {"SITE_MODE": "local"}):
            result = _resolve_origin_regex()
            assert result is not None


# ---------------------------------------------------------------------------
# EnsureCorsOnErrorMiddleware
# ---------------------------------------------------------------------------


class TestEnsureCorsOnErrorMiddleware:
    def test_origin_in_allowlist(self) -> None:
        mw = EnsureCorsOnErrorMiddleware(
            MagicMock(), allowed_origins=["https://example.com"], origin_regex=None,
        )
        assert mw._origin_allowed("https://example.com") is True
        assert mw._origin_allowed("https://other.com") is False
        assert mw._origin_allowed(None) is False

    def test_origin_matches_regex(self) -> None:
        mw = EnsureCorsOnErrorMiddleware(
            MagicMock(), allowed_origins=[], origin_regex=r"https://.*\.example\.com",
        )
        assert mw._origin_allowed("https://sub.example.com") is True
        assert mw._origin_allowed("https://other.com") is False


# ---------------------------------------------------------------------------
# SSEAwareGZipMiddleware
# ---------------------------------------------------------------------------


class TestSSEAwareGZipMiddleware:
    @pytest.mark.asyncio
    async def test_sse_path_skips_gzip(self) -> None:
        inner_app = AsyncMock()
        mw = SSEAwareGZipMiddleware(inner_app, minimum_size=500)

        scope = {"type": "http", "path": "/api/v1/messages/stream"}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        inner_app.assert_called_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_metrics_path_skips_gzip(self) -> None:
        inner_app = AsyncMock()
        mw = SSEAwareGZipMiddleware(inner_app, minimum_size=500)

        scope = {"type": "http", "path": "/api/v1/internal/metrics"}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)
        inner_app.assert_called_once()


# ---------------------------------------------------------------------------
# register_middleware
# ---------------------------------------------------------------------------


class TestRegisterMiddleware:
    @patch("app.core.middleware_setup.settings")
    @patch("app.core.middleware_setup.perf_counters_enabled", return_value=False)
    def test_non_production_registration(self, mock_perf: MagicMock, mock_settings: MagicMock) -> None:
        mock_settings.environment = "development"
        mock_settings.preview_frontend_domain = "preview.example.com"
        mock_settings.prod_frontend_origins_csv = ""

        app = MagicMock()
        app.state = MagicMock()
        app.state.sentry_enabled = False

        middleware_module._BGC_ENV_LOGGED = False
        with patch.dict(os.environ, {"SITE_MODE": "local"}):
            register_middleware(app)

        # Should not add HTTPS redirect in non-production
        assert not any(
            "https_redirect" in str(call) for call in app.add_middleware.call_args_list
        )
        middleware_module._BGC_ENV_LOGGED = False

    @patch("app.core.middleware_setup.settings")
    @patch("app.core.middleware_setup.perf_counters_enabled", return_value=True)
    @patch("app.core.middleware_setup.create_https_redirect_middleware")
    def test_production_registration(
        self, mock_https: MagicMock, mock_perf: MagicMock, mock_settings: MagicMock
    ) -> None:
        mock_settings.environment = "production"
        mock_settings.prod_frontend_origins_csv = "https://app.example.com"

        app = MagicMock()
        app.state = MagicMock()
        app.state.sentry_enabled = True

        middleware_module._BGC_ENV_LOGGED = False
        with patch.dict(os.environ, {"SITE_MODE": "prod"}):
            register_middleware(app)

        mock_https.assert_called_once_with(force_https=True)
        middleware_module._BGC_ENV_LOGGED = False

    @patch("app.core.middleware_setup.settings")
    def test_wildcard_origin_raises(self, mock_settings: MagicMock) -> None:
        mock_settings.environment = "development"

        app = MagicMock()
        app.state = MagicMock()

        middleware_module._BGC_ENV_LOGGED = False
        with patch.dict(os.environ, {"SITE_MODE": "local", "CORS_ALLOW_ORIGINS": "*"}):
            with pytest.raises(RuntimeError, match="CORS allow_origins cannot include"):
                register_middleware(app)
        middleware_module._BGC_ENV_LOGGED = False
