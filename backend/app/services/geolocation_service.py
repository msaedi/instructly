# backend/app/services/geolocation_service.py
"""
GeolocationService for NYC-specific tracking and analytics.

Provides IP geolocation services with:
- NYC borough detection
- Redis caching for performance
- Privacy-aware (no street-level data)
- Rate limiting protection
"""

import hashlib
import ipaddress
import logging
from typing import Dict, Optional

import httpx
from sqlalchemy.orm import Session

from .base import BaseService

logger = logging.getLogger(__name__)


class GeolocationService(BaseService):
    """
    Service for converting IP addresses to geographic information.

    Focuses on NYC market with special borough detection while maintaining
    privacy by only storing city/state/country level information.
    """

    # NYC boroughs mapping for enhanced local tracking
    NYC_BOROUGHS = {
        "Brooklyn": "Brooklyn",
        "Queens": "Queens",
        "Manhattan": "Manhattan",
        "The Bronx": "Bronx",
        "Staten Island": "Staten Island",
        # Alternative names
        "Bronx": "Bronx",
        "New York": "Manhattan",  # Most APIs return "New York" for Manhattan
    }

    def __init__(self, db: Session, cache_service=None):
        super().__init__(db)
        self.cache_service = cache_service
        self.client = httpx.AsyncClient(timeout=5.0)

    async def get_location_from_ip(self, ip_address: str) -> Optional[Dict]:
        """
        Get geographic location from IP address.

        Args:
            ip_address: IPv4 or IPv6 address to lookup

        Returns:
            Dict with location data or None if lookup fails
            {
                "country_code": "US",
                "country_name": "United States",
                "state": "New York",
                "city": "New York",
                "borough": "Manhattan",  # Only for NYC
                "postal_code": "10001",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "is_nyc": True,
                "timezone": "America/New_York"
            }
        """
        if not self._is_valid_ip(ip_address):
            logger.warning(f"Invalid IP address format: {ip_address}")
            return None

        # Skip private/local IPs
        if self._is_private_ip(ip_address):
            logger.debug(f"Skipping private IP: {ip_address}")
            return self._get_default_location()

        # Check cache first
        cache_key = f"geo:ip:{self._hash_ip(ip_address)}"
        if self.cache_service:
            cached_result = await self.cache_service.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for IP geolocation: {ip_address[:8]}...")
                return cached_result

        try:
            # Use multiple services for reliability
            location_data = await self._lookup_with_fallback(ip_address)

            if location_data:
                # Enhance with NYC-specific data
                location_data = self._enhance_nyc_data(location_data)

                # Cache for 24 hours (86400 seconds)
                if self.cache_service:
                    await self.cache_service.set(cache_key, location_data, ttl=86400)

                logger.info(f"Geolocation lookup successful for {ip_address[:8]}...")
                return location_data
            else:
                logger.warning(f"No location data found for IP: {ip_address[:8]}...")
                return self._get_default_location()

        except Exception as e:
            logger.error(f"Geolocation lookup failed for {ip_address[:8]}...: {str(e)}")
            return self._get_default_location()

    async def _lookup_with_fallback(self, ip_address: str) -> Optional[Dict]:
        """Try multiple geolocation services with fallback."""

        # Primary service: ipapi.co (free tier: 1000/day)
        try:
            location_data = await self._lookup_ipapi(ip_address)
            if location_data:
                return location_data
        except Exception as e:
            logger.warning(f"ipapi.co lookup failed: {str(e)}")

        # Fallback service: ip-api.com (free tier: 1000/hour)
        try:
            location_data = await self._lookup_ipapi_com(ip_address)
            if location_data:
                return location_data
        except Exception as e:
            logger.warning(f"ip-api.com lookup failed: {str(e)}")

        return None

    async def _lookup_ipapi(self, ip_address: str) -> Optional[Dict]:
        """Lookup using ipapi.co service."""
        url = f"https://ipapi.co/{ip_address}/json/"

        async with self.client as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("error"):
                logger.warning(f"ipapi.co error: {data.get('reason', 'Unknown error')}")
                return None

            return {
                "country_code": data.get("country_code"),
                "country_name": data.get("country_name"),
                "state": data.get("region"),
                "city": data.get("city"),
                "postal_code": data.get("postal"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "timezone": data.get("timezone"),
            }

    async def _lookup_ipapi_com(self, ip_address: str) -> Optional[Dict]:
        """Lookup using ip-api.com service."""
        url = f"http://ip-api.com/json/{ip_address}"

        async with self.client as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.warning(f"ip-api.com error: {data.get('message', 'Unknown error')}")
                return None

            return {
                "country_code": data.get("countryCode"),
                "country_name": data.get("country"),
                "state": data.get("regionName"),
                "city": data.get("city"),
                "postal_code": data.get("zip"),
                "latitude": data.get("lat"),
                "longitude": data.get("lon"),
                "timezone": data.get("timezone"),
            }

    def _enhance_nyc_data(self, location_data: Dict) -> Dict:
        """Enhance location data with NYC-specific information."""
        city = location_data.get("city", "")
        state = location_data.get("state", "")

        # Debug logging
        logger.debug(f"NYC detection - city: '{city}', state: '{state}'")

        # Check if this is NYC - normalize and strip whitespace
        is_nyc = (
            (
                state.strip().lower() in ["new york", "ny"]
                and city.strip().lower()
                in ["new york", "brooklyn", "queens", "bronx", "staten island", "the bronx", "manhattan"]
            )
            if state and city
            else False
        )

        location_data["is_nyc"] = is_nyc

        if is_nyc:
            # Map to standardized borough name
            borough = self.NYC_BOROUGHS.get(city)
            if borough:
                location_data["borough"] = borough

            # Ensure city is "New York" for NYC locations
            location_data["city"] = "New York"

        return location_data

    def _is_valid_ip(self, ip_address: str) -> bool:
        """Check if string is a valid IP address."""
        try:
            ipaddress.ip_address(ip_address)
            return True
        except ValueError:
            return False

    def _is_private_ip(self, ip_address: str) -> bool:
        """Check if IP is private/local."""
        try:
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return True

    def _hash_ip(self, ip_address: str) -> str:
        """Create privacy-aware hash of IP address."""
        return hashlib.sha256(ip_address.encode()).hexdigest()[:16]

    def _get_default_location(self) -> Dict:
        """Return default location for private/invalid IPs."""
        return {
            "country_code": "US",
            "country_name": "United States",
            "state": "New York",
            "city": "New York",
            "borough": None,
            "postal_code": None,
            "latitude": 40.7128,
            "longitude": -74.0060,
            "is_nyc": False,  # Don't assume NYC for unknown IPs
            "timezone": "America/New_York",
        }

    def get_ip_from_request(self, request) -> str:
        """
        Extract real IP address from request, handling proxies.

        Checks headers in order of preference:
        1. X-Forwarded-For (most common proxy header)
        2. X-Real-IP (nginx)
        3. CF-Connecting-IP (Cloudflare)
        4. Remote address
        """
        # Check proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, first is the original client
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

        # Fallback to direct connection
        return request.client.host if request.client else "127.0.0.1"

    async def close(self):
        """Clean up HTTP client."""
        await self.client.aclose()
