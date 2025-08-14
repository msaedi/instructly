# backend/app/services/device_tracking_service.py
"""
DeviceTrackingService for analytics and user experience optimization.

Provides device/browser detection services with:
- User agent parsing (browser, OS, device type)
- Screen/viewport resolution tracking
- Connection type detection
- Performance-aware (cached results)
"""

import logging
import re
from typing import Dict, Optional

from sqlalchemy.orm import Session
from user_agents import parse

from .base import BaseService

logger = logging.getLogger(__name__)


class DeviceTrackingService(BaseService):
    """
    Service for detecting and tracking device/browser information.

    Extracts meaningful analytics data from user agents and client hints
    to understand user experience and optimize for different devices.
    """

    # Device type patterns for fallback detection
    MOBILE_PATTERNS = [r"Mobile", r"Android", r"iPhone", r"iPad", r"iPod", r"BlackBerry", r"webOS", r"Windows Phone"]

    TABLET_PATTERNS = [r"iPad", r"Android.*Tablet", r"Kindle", r"Silk", r"PlayBook"]

    # Connection type indicators from user agent
    CONNECTION_INDICATORS = {
        "slow-2g": ["2G", "EDGE", "slow"],
        "2g": ["2G", "EDGE"],
        "3g": ["3G", "HSPA", "UMTS"],
        "4g": ["4G", "LTE"],
        "5g": ["5G"],
    }

    def __init__(self, db: Session):
        super().__init__(db)
        self._user_agent_cache = {}  # Simple in-memory cache for parsing results

    def parse_user_agent(self, user_agent: str) -> Dict:  # no-metrics
        """
        Parse user agent string to extract device/browser information.

        Args:
            user_agent: Raw user agent string from request headers

        Returns:
            Dict with parsed information:
            {
                "browser_name": "Chrome",
                "browser_version": "91.0.4472.124",
                "os_family": "Windows",
                "os_version": "10",
                "device_family": "Other",
                "device_type": "desktop",  # desktop, mobile, tablet
                "is_mobile": False,
                "is_tablet": False,
                "is_bot": False,
                "raw_user_agent": "Mozilla/5.0..."
            }
        """
        if not user_agent:
            return self._get_default_device_info()

        # Check cache first
        cache_key = hash(user_agent)
        if cache_key in self._user_agent_cache:
            return self._user_agent_cache[cache_key]

        try:
            # Parse using user-agents library
            parsed = parse(user_agent)

            # Determine device type
            device_type = self._determine_device_type(parsed, user_agent)

            device_info = {
                "browser_name": parsed.browser.family,
                "browser_version": parsed.browser.version_string,
                "os_family": parsed.os.family,
                "os_version": parsed.os.version_string,
                "device_family": parsed.device.family,
                "device_type": device_type,
                "is_mobile": parsed.is_mobile,
                "is_tablet": parsed.is_tablet,
                "is_bot": parsed.is_bot,
                "raw_user_agent": user_agent,
            }

            # Cache the result
            self._user_agent_cache[cache_key] = device_info

            logger.debug(f"Parsed user agent: {device_type} - {parsed.browser.family}")
            return device_info

        except Exception as e:
            logger.warning(f"Failed to parse user agent: {str(e)}")
            return self._get_default_device_info(user_agent)

    def _determine_device_type(self, parsed, user_agent: str) -> str:
        """Determine device type with fallback patterns."""
        # Use library's classification first
        if parsed.is_tablet:
            return "tablet"
        elif parsed.is_mobile:
            return "mobile"

        # Fallback to pattern matching for edge cases
        if any(re.search(pattern, user_agent, re.IGNORECASE) for pattern in self.TABLET_PATTERNS):
            return "tablet"
        elif any(re.search(pattern, user_agent, re.IGNORECASE) for pattern in self.MOBILE_PATTERNS):
            return "mobile"

        return "desktop"

    def extract_client_hints(self, request) -> Dict:  # no-metrics
        """
        Extract Client Hints from request headers for modern browsers.

        Client Hints provide more accurate device information than user agents.
        """
        hints = {}

        # Device information
        hints["device_memory"] = request.headers.get("Device-Memory")
        hints["viewport_width"] = request.headers.get("Viewport-Width")
        hints["screen_width"] = request.headers.get("Width")
        hints["dpr"] = request.headers.get("DPR")  # Device Pixel Ratio

        # Network information
        hints["downlink"] = request.headers.get("Downlink")
        hints["ect"] = request.headers.get("ECT")  # Effective Connection Type
        hints["rtt"] = request.headers.get("RTT")  # Round Trip Time

        # Platform information
        hints["platform"] = request.headers.get("Sec-CH-UA-Platform")
        hints["mobile"] = request.headers.get("Sec-CH-UA-Mobile")
        hints["ua_full_version"] = request.headers.get("Sec-CH-UA-Full-Version")

        # Remove None values
        return {k: v for k, v in hints.items() if v is not None}

    def get_connection_type(self, request) -> Optional[str]:  # no-metrics
        """
        Determine connection type from various indicators.

        Returns connection type: wifi, cellular, ethernet, slow-2g, 2g, 3g, 4g, 5g
        """
        # Check Client Hints first (most accurate)
        ect = request.headers.get("ECT")  # Effective Connection Type
        if ect:
            return ect.lower()

        # Check for connection type header (some networks provide this)
        connection_type = request.headers.get("Connection-Type")
        if connection_type:
            return connection_type.lower()

        # Fallback to user agent analysis
        user_agent = request.headers.get("User-Agent", "")
        for conn_type, indicators in self.CONNECTION_INDICATORS.items():
            if any(indicator in user_agent for indicator in indicators):
                return conn_type

        # Check downlink speed if available
        downlink = request.headers.get("Downlink")
        if downlink:
            try:
                speed = float(downlink)
                if speed < 0.15:
                    return "slow-2g"
                elif speed < 0.75:
                    return "2g"
                elif speed < 2.0:
                    return "3g"
                else:
                    return "4g"
            except (ValueError, TypeError):
                pass

        return None

    @BaseService.measure_operation("get_device_context_from_request")
    def get_device_context_from_request(self, request) -> Dict:
        """
        Extract complete device context from HTTP request.

        Combines user agent parsing, client hints, and connection detection.
        """
        user_agent = request.headers.get("User-Agent", "")

        # Parse user agent
        device_info = self.parse_user_agent(user_agent)

        # Add client hints
        client_hints = self.extract_client_hints(request)
        if client_hints:
            device_info["client_hints"] = client_hints

        # Add connection information
        connection_type = self.get_connection_type(request)
        if connection_type:
            device_info["connection_type"] = connection_type

        # Add request-specific information
        device_info["accept_language"] = request.headers.get("Accept-Language")
        device_info["accept_encoding"] = request.headers.get("Accept-Encoding")
        device_info["referer"] = request.headers.get("Referer")

        return device_info

    def _get_default_device_info(self, user_agent: str = None) -> Dict:
        """Return default device info for unparseable user agents."""
        return {
            "browser_name": "Unknown",
            "browser_version": "",
            "os_family": "Unknown",
            "os_version": "",
            "device_family": "Other",
            "device_type": "desktop",  # Default assumption
            "is_mobile": False,
            "is_tablet": False,
            "is_bot": False,
            "raw_user_agent": user_agent or "",
        }

    def format_for_analytics(self, device_context: Dict) -> Dict:  # no-metrics
        """
        Format device context for storage in analytics tables.

        Returns optimized data structure for search_events.device_type and
        search_events.browser_info columns.
        """
        # Extract key fields for device_type column
        device_type = device_context.get("device_type", "desktop")

        # Create compact browser_info JSON
        browser_info = {
            "browser": {
                "name": device_context.get("browser_name"),
                "version": device_context.get("browser_version"),
            },
            "os": {
                "family": device_context.get("os_family"),
                "version": device_context.get("os_version"),
            },
            "device": {
                "family": device_context.get("device_family"),
                "is_mobile": device_context.get("is_mobile", False),
                "is_tablet": device_context.get("is_tablet", False),
                "is_bot": device_context.get("is_bot", False),
            },
        }

        # Add client hints if available
        if "client_hints" in device_context:
            browser_info["hints"] = device_context["client_hints"]

        # Add language and encoding preferences
        if device_context.get("accept_language"):
            browser_info["language"] = device_context["accept_language"][:50]  # Truncate

        return {
            "device_type": device_type,
            "browser_info": browser_info,
            "connection_type": device_context.get("connection_type"),
        }

    def get_analytics_summary(self, device_contexts: list) -> Dict:  # no-metrics
        """
        Generate analytics summary from multiple device contexts.

        Useful for admin dashboards and usage reports.
        """
        if not device_contexts:
            return {}

        # Count device types
        device_types = {}
        browsers = {}
        operating_systems = {}

        for context in device_contexts:
            # Device types
            device_type = context.get("device_type", "desktop")
            device_types[device_type] = device_types.get(device_type, 0) + 1

            # Browsers
            browser = context.get("browser_name", "Unknown")
            browsers[browser] = browsers.get(browser, 0) + 1

            # Operating systems
            os_family = context.get("os_family", "Unknown")
            operating_systems[os_family] = operating_systems.get(os_family, 0) + 1

        total = len(device_contexts)

        return {
            "total_sessions": total,
            "device_types": {
                k: {"count": v, "percentage": round(v / total * 100, 1)}
                for k, v in sorted(device_types.items(), key=lambda x: x[1], reverse=True)
            },
            "top_browsers": {
                k: {"count": v, "percentage": round(v / total * 100, 1)}
                for k, v in sorted(browsers.items(), key=lambda x: x[1], reverse=True)[:10]
            },
            "top_os": {
                k: {"count": v, "percentage": round(v / total * 100, 1)}
                for k, v in sorted(operating_systems.items(), key=lambda x: x[1], reverse=True)[:10]
            },
        }
