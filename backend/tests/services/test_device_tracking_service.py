# backend/tests/services/test_device_tracking_service.py
"""
Tests for DeviceTrackingService.

Tests user agent parsing, device type detection, client hints extraction,
and analytics formatting.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.services.device_tracking_service import DeviceTrackingService


class TestDeviceTrackingService:
    """Test DeviceTrackingService functionality."""

    @pytest.fixture
    def service(self, db):
        """Create DeviceTrackingService instance."""
        return DeviceTrackingService(db)

    def _create_mock_request(self, headers_data):
        """Helper to create mock request with headers."""
        mock_request = Mock()
        mock_request.headers = Mock()
        mock_request.headers.get = lambda key, default=None: headers_data.get(key, default)
        return mock_request

    def test_parse_user_agent_chrome_desktop(self, service):
        """Test parsing Chrome desktop user agent."""
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

        result = service.parse_user_agent(ua)

        assert result["browser_name"] == "Chrome"
        assert result["browser_version"].startswith("91.0")
        assert result["os_family"] == "Windows"
        assert result["os_version"].startswith("10")
        assert result["device_type"] == "desktop"
        assert result["is_mobile"] is False
        assert result["is_tablet"] is False
        assert result["is_bot"] is False
        assert result["raw_user_agent"] == ua

    def test_parse_user_agent_iphone(self, service):
        """Test parsing iPhone user agent."""
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"

        result = service.parse_user_agent(ua)

        assert result["browser_name"] == "Mobile Safari"
        assert result["os_family"] == "iOS"
        assert result["device_type"] == "mobile"
        assert result["is_mobile"] is True
        assert result["is_tablet"] is False
        assert result["device_family"] == "iPhone"

    def test_parse_user_agent_ipad(self, service):
        """Test parsing iPad user agent."""
        ua = "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"

        result = service.parse_user_agent(ua)

        assert result["browser_name"] == "Mobile Safari"
        assert result["os_family"] == "iOS"
        assert result["device_type"] == "tablet"
        assert result["is_mobile"] is False
        assert result["is_tablet"] is True
        assert result["device_family"] == "iPad"

    def test_parse_user_agent_android_mobile(self, service):
        """Test parsing Android mobile user agent."""
        ua = "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36"

        result = service.parse_user_agent(ua)

        assert result["browser_name"] == "Chrome Mobile"
        assert result["os_family"] == "Android"
        assert result["device_type"] == "mobile"
        assert result["is_mobile"] is True
        assert result["is_tablet"] is False

    def test_parse_user_agent_bot(self, service):
        """Test parsing bot user agent."""
        ua = "Googlebot/2.1 (+http://www.google.com/bot.html)"

        result = service.parse_user_agent(ua)

        assert result["is_bot"] is True
        assert result["device_type"] == "desktop"  # Default for bots

    def test_parse_user_agent_empty(self, service):
        """Test parsing empty user agent."""
        result = service.parse_user_agent("")

        assert result["browser_name"] == "Unknown"
        assert result["os_family"] == "Unknown"
        assert result["device_type"] == "desktop"
        assert result["is_mobile"] is False
        assert result["is_tablet"] is False
        assert result["is_bot"] is False

    def test_parse_user_agent_caching(self, service):
        """Test that user agent parsing results are cached."""
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        # First call
        result1 = service.parse_user_agent(ua)
        # Second call should use cache
        result2 = service.parse_user_agent(ua)

        assert result1 == result2
        # Verify cache was used (same object reference)
        cache_key = hash(ua)
        assert cache_key in service._user_agent_cache

    def test_extract_client_hints(self, service):
        """Test extracting client hints from request headers."""
        headers_data = {
            "Device-Memory": "8",
            "Viewport-Width": "1920",
            "Width": "1920",
            "DPR": "1",
            "Downlink": "10.0",
            "ECT": "4g",
            "RTT": "50",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Full-Version": '"91.0.4472.124"',
            "Some-Other-Header": "ignored",  # Should be ignored
        }

        mock_request = Mock()
        mock_request.headers = Mock()
        mock_request.headers.get = lambda key, default=None: headers_data.get(key, default)

        hints = service.extract_client_hints(mock_request)

        assert hints["device_memory"] == "8"
        assert hints["viewport_width"] == "1920"
        assert hints["dpr"] == "1"
        assert hints["downlink"] == "10.0"
        assert hints["ect"] == "4g"
        assert hints["platform"] == '"Windows"'
        assert hints["mobile"] == "?0"
        assert "Some-Other-Header" not in hints

    def test_extract_client_hints_empty(self, service):
        """Test extracting client hints when none are present."""
        mock_request = self._create_mock_request({})

        hints = service.extract_client_hints(mock_request)

        assert hints == {}

    def test_get_connection_type_client_hints(self, service):
        """Test connection type detection from client hints."""
        mock_request = self._create_mock_request({"ECT": "4g"})

        connection_type = service.get_connection_type(mock_request)

        assert connection_type == "4g"

    def test_get_connection_type_downlink(self, service):
        """Test connection type detection from downlink speed."""
        mock_request = self._create_mock_request({"Downlink": "0.5"})  # 2G speed

        connection_type = service.get_connection_type(mock_request)

        assert connection_type == "2g"

    def test_get_connection_type_user_agent(self, service):
        """Test connection type detection from user agent."""
        mock_request = self._create_mock_request({"User-Agent": "Mozilla/5.0... 4G Mobile"})

        connection_type = service.get_connection_type(mock_request)

        assert connection_type == "4g"

    def test_get_connection_type_none(self, service):
        """Test connection type when no indicators present."""
        mock_request = self._create_mock_request({})

        connection_type = service.get_connection_type(mock_request)

        assert connection_type is None

    def test_get_device_context_from_request(self, service):
        """Test complete device context extraction."""
        headers_data = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "ECT": "4g",
            "Device-Memory": "8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://google.com",
        }
        mock_request = self._create_mock_request(headers_data)

        context = service.get_device_context_from_request(mock_request)

        # Should include parsed user agent
        assert context["browser_name"] == "Chrome"
        assert context["device_type"] == "desktop"

        # Should include client hints
        assert "client_hints" in context
        assert context["client_hints"]["device_memory"] == "8"

        # Should include connection type
        assert context["connection_type"] == "4g"

        # Should include request headers
        assert context["accept_language"] == "en-US,en;q=0.9"
        assert context["referer"] == "https://google.com"

    def test_format_for_analytics(self, service):
        """Test formatting device context for analytics storage."""
        device_context = {
            "browser_name": "Chrome",
            "browser_version": "91.0.4472.124",
            "os_family": "Windows",
            "os_version": "10",
            "device_family": "Other",
            "device_type": "desktop",
            "is_mobile": False,
            "is_tablet": False,
            "is_bot": False,
            "connection_type": "4g",
            "accept_language": "en-US,en;q=0.9",
            "client_hints": {"device_memory": "8"},
        }

        formatted = service.format_for_analytics(device_context)

        assert formatted["device_type"] == "desktop"
        assert formatted["connection_type"] == "4g"

        browser_info = formatted["browser_info"]
        assert browser_info["browser"]["name"] == "Chrome"
        assert browser_info["browser"]["version"] == "91.0.4472.124"
        assert browser_info["os"]["family"] == "Windows"
        assert browser_info["device"]["is_mobile"] is False
        assert browser_info["hints"]["device_memory"] == "8"
        assert browser_info["language"] == "en-US,en;q=0.9"

    def test_get_analytics_summary(self, service):
        """Test analytics summary generation."""
        device_contexts = [
            {"device_type": "desktop", "browser_name": "Chrome", "os_family": "Windows"},
            {"device_type": "mobile", "browser_name": "Safari", "os_family": "iOS"},
            {"device_type": "desktop", "browser_name": "Chrome", "os_family": "macOS"},
            {"device_type": "mobile", "browser_name": "Chrome", "os_family": "Android"},
        ]

        summary = service.get_analytics_summary(device_contexts)

        assert summary["total_sessions"] == 4

        # Device types
        device_types = summary["device_types"]
        assert device_types["desktop"]["count"] == 2
        assert device_types["desktop"]["percentage"] == 50.0
        assert device_types["mobile"]["count"] == 2

        # Browsers
        browsers = summary["top_browsers"]
        assert browsers["Chrome"]["count"] == 3
        assert browsers["Chrome"]["percentage"] == 75.0
        assert browsers["Safari"]["count"] == 1

        # Operating systems
        os_data = summary["top_os"]
        assert len(os_data) == 4  # Windows, iOS, macOS, Android

    def test_get_analytics_summary_empty(self, service):
        """Test analytics summary with empty list."""
        summary = service.get_analytics_summary([])

        assert summary == {}

    def test_device_type_patterns(self, service):
        """Test device type detection patterns."""
        # Test mobile patterns
        mobile_ua = "Mozilla/5.0 (Android 11; Mobile; rv:68.0) Gecko/68.0 Firefox/88.0"
        parsed_mobile = service.parse_user_agent(mobile_ua)
        assert parsed_mobile["device_type"] == "mobile"

        # Test tablet patterns
        tablet_ua = "Mozilla/5.0 (Android 11; Tablet; rv:68.0) Gecko/68.0 Firefox/88.0"
        parsed_tablet = service.parse_user_agent(tablet_ua)
        assert parsed_tablet["device_type"] in ["tablet", "mobile"]  # Depends on parsing library

    def test_connection_indicators(self, service):
        """Test connection type indicators mapping."""
        # Test all connection types
        speed_tests = [
            ("0.1", "slow-2g"),
            ("0.5", "2g"),
            ("1.5", "3g"),
            ("5.0", "4g"),
        ]

        for speed, expected_type in speed_tests:
            mock_request = self._create_mock_request({"Downlink": speed})

            connection_type = service.get_connection_type(mock_request)
            assert connection_type == expected_type

    def test_parse_user_agent_returns_default_when_parser_errors(self, service):
        with patch("app.services.device_tracking_service.parse", side_effect=RuntimeError("parse boom")):
            result = service.parse_user_agent("broken-user-agent")

        assert result["browser_name"] == "Unknown"
        assert result["raw_user_agent"] == "broken-user-agent"

    def test_determine_device_type_uses_pattern_fallbacks(self, service):
        parsed = SimpleNamespace(is_tablet=False, is_mobile=False)

        assert service._determine_device_type(parsed, "Mozilla/5.0 Android Tablet") == "tablet"
        assert service._determine_device_type(parsed, "Mozilla/5.0 (iPhone)") == "mobile"

    def test_get_connection_type_prefers_connection_type_header(self, service):
        mock_request = self._create_mock_request({"Connection-Type": "Cellular"})

        connection_type = service.get_connection_type(mock_request)

        assert connection_type == "cellular"

    def test_get_connection_type_ignores_invalid_downlink_values(self, service):
        mock_request = self._create_mock_request({"Downlink": "not-a-number"})

        connection_type = service.get_connection_type(mock_request)

        assert connection_type is None

    def test_get_device_context_without_optional_hints_or_connection(self, service, monkeypatch):
        base_context = {
            "browser_name": "Chrome",
            "browser_version": "1",
            "os_family": "Windows",
            "os_version": "11",
            "device_family": "Other",
            "device_type": "desktop",
            "is_mobile": False,
            "is_tablet": False,
            "is_bot": False,
            "raw_user_agent": "ua",
        }
        monkeypatch.setattr(service, "parse_user_agent", lambda _ua: dict(base_context))
        monkeypatch.setattr(service, "extract_client_hints", lambda _request: {})
        monkeypatch.setattr(service, "get_connection_type", lambda _request: None)

        mock_request = self._create_mock_request({"User-Agent": "ua"})
        context = service.get_device_context_from_request(mock_request)

        assert "client_hints" not in context
        assert "connection_type" not in context
