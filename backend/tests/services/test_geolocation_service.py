# backend/tests/services/test_geolocation_service.py
"""
Tests for GeolocationService.

Tests IP geolocation functionality, NYC borough detection,
caching behavior, and privacy features.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.geolocation_service import GeolocationService


class TestGeolocationService:
    """Test GeolocationService functionality."""

    @pytest.fixture
    def mock_cache_service(self):
        """Mock cache service."""
        cache = AsyncMock()
        cache.get.return_value = None  # Default: no cache hit
        return cache

    @pytest.fixture
    def service(self, db, mock_cache_service):
        """Create GeolocationService instance."""
        return GeolocationService(db, mock_cache_service)

    def test_nyc_boroughs_mapping(self, service):
        """Test NYC boroughs are properly mapped."""
        assert "Brooklyn" in service.NYC_BOROUGHS
        assert "Manhattan" in service.NYC_BOROUGHS
        assert "Queens" in service.NYC_BOROUGHS
        assert "Bronx" in service.NYC_BOROUGHS
        assert "Staten Island" in service.NYC_BOROUGHS

        # Test alternative names
        assert service.NYC_BOROUGHS["New York"] == "Manhattan"
        assert service.NYC_BOROUGHS["The Bronx"] == "Bronx"

    def test_is_valid_ip(self, service):
        """Test IP address validation."""
        # Valid IPs
        assert service._is_valid_ip("192.168.1.1") is True
        assert service._is_valid_ip("8.8.8.8") is True
        assert service._is_valid_ip("2001:db8::1") is True

        # Invalid IPs
        assert service._is_valid_ip("invalid") is False
        assert service._is_valid_ip("999.999.999.999") is False
        assert service._is_valid_ip("") is False

    def test_is_private_ip(self, service):
        """Test private IP detection."""
        # Private IPs
        assert service._is_private_ip("192.168.1.1") is True
        assert service._is_private_ip("10.0.0.1") is True
        assert service._is_private_ip("127.0.0.1") is True

        # Public IPs
        assert service._is_private_ip("8.8.8.8") is False
        assert service._is_private_ip("1.1.1.1") is False

    def test_hash_ip(self, service):
        """Test IP hashing for privacy."""
        ip = "8.8.8.8"
        hash1 = service._hash_ip(ip)
        hash2 = service._hash_ip(ip)

        # Same IP should produce same hash
        assert hash1 == hash2

        # Hash should be 16 characters (truncated SHA-256)
        assert len(hash1) == 16

        # Different IPs should produce different hashes
        assert service._hash_ip("8.8.8.8") != service._hash_ip("1.1.1.1")

    def test_enhance_nyc_data(self, service):
        """Test NYC data enhancement."""
        # Test Manhattan
        data = {"city": "New York", "state": "New York"}
        enhanced = service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is True
        assert enhanced["borough"] == "Manhattan"
        assert enhanced["city"] == "New York"

        # Test Brooklyn
        data = {"city": "Brooklyn", "state": "NY"}
        enhanced = service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is True
        assert enhanced["borough"] == "Brooklyn"
        assert enhanced["city"] == "New York"

        # Test non-NYC
        data = {"city": "Los Angeles", "state": "California"}
        enhanced = service._enhance_nyc_data(data)
        assert enhanced["is_nyc"] is False
        assert "borough" not in enhanced
        assert enhanced["city"] == "Los Angeles"

    def test_get_default_location(self, service):
        """Test default location for private IPs."""
        default = service._get_default_location()

        assert default["country_code"] == "US"
        assert default["state"] == "New York"
        assert default["city"] == "New York"
        assert default["is_nyc"] is False  # Don't assume NYC for unknown
        assert default["latitude"] == 40.7128
        assert default["longitude"] == -74.0060

    @pytest.mark.asyncio
    async def test_private_ip_returns_default(self, service):
        """Test that private IPs return default location."""
        result = await service.get_location_from_ip("192.168.1.1")

        assert result is not None
        assert result["country_code"] == "US"
        assert result["is_nyc"] is False

    @pytest.mark.asyncio
    async def test_invalid_ip_returns_none(self, service):
        """Test that invalid IPs return None."""
        result = await service.get_location_from_ip("invalid-ip")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, service, mock_cache_service):
        """Test cache hit returns cached data."""
        cached_data = {"city": "New York", "is_nyc": True}
        mock_cache_service.get.return_value = cached_data

        result = await service.get_location_from_ip("8.8.8.8")

        assert result == cached_data
        mock_cache_service.get.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_successful_lookup_ipapi(self, mock_client_class, service, mock_cache_service):
        """Test successful geolocation lookup using ipapi.co."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.json.return_value = {
            "country_code": "US",
            "country_name": "United States",
            "region": "New York",
            "city": "Brooklyn",
            "postal": "11201",
            "latitude": 40.6892,
            "longitude": -73.9442,
            "timezone": "America/New_York",
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        service.client = mock_client

        result = await service.get_location_from_ip("8.8.8.8")

        assert result is not None
        assert result["country_code"] == "US"
        assert result["city"] == "New York"  # Should be normalized for NYC
        assert result["borough"] == "Brooklyn"
        assert result["is_nyc"] is True

        # Verify caching
        mock_cache_service.set.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_lookup_fallback_to_second_service(self, mock_client_class, service):
        """Test fallback to second service when first fails."""
        # First service fails
        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            Exception("First service failed"),  # ipapi.co fails
            Mock(
                json=lambda: {
                    "status": "success",
                    "countryCode": "US",
                    "country": "United States",
                    "regionName": "New York",
                    "city": "Manhattan",
                    "zip": "10001",
                    "lat": 40.7128,
                    "lon": -74.0060,
                    "timezone": "America/New_York",
                }
            ),  # ip-api.com succeeds
        ]
        mock_client.__aenter__.return_value = mock_client
        service.client = mock_client

        result = await service.get_location_from_ip("8.8.8.8")

        assert result is not None
        assert result["country_code"] == "US"
        assert result["borough"] == "Manhattan"
        assert result["is_nyc"] is True

    def test_get_ip_from_request_forwarded_for(self, service):
        """Test IP extraction from X-Forwarded-For header."""
        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}

        ip = service.get_ip_from_request(mock_request)
        assert ip == "1.2.3.4"

    def test_get_ip_from_request_real_ip(self, service):
        """Test IP extraction from X-Real-IP header."""
        mock_request = Mock()
        mock_request.headers = {"X-Real-IP": "1.2.3.4"}

        ip = service.get_ip_from_request(mock_request)
        assert ip == "1.2.3.4"

    def test_get_ip_from_request_cloudflare(self, service):
        """Test IP extraction from CF-Connecting-IP header."""
        mock_request = Mock()
        mock_request.headers = {"CF-Connecting-IP": "1.2.3.4"}

        ip = service.get_ip_from_request(mock_request)
        assert ip == "1.2.3.4"

    def test_get_ip_from_request_fallback(self, service):
        """Test fallback to client host."""
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client.host = "1.2.3.4"

        ip = service.get_ip_from_request(mock_request)
        assert ip == "1.2.3.4"

    def test_get_ip_from_request_no_client(self, service):
        """Test fallback when no client info available."""
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = None

        ip = service.get_ip_from_request(mock_request)
        assert ip == "127.0.0.1"
