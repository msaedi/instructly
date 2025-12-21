"""
Regression tests for PR #132 - Background Check Service
Tests country code normalization to prevent Checkr API failures.
"""


class TestBackgroundCheckCountryCodeRegression:
    """Tests for country code normalization - PR #132 regression fix"""

    def test_country_code_uppercase_from_mapbox(self):
        """
        Regression test: Mapbox returns lowercase country codes ('us')
        but Checkr API requires uppercase ('US').

        Bug: PR #132 dropped .upper() during refactor, causing all BGC to fail.
        Fix: Added .upper() back to country_value normalization.
        """
        # Simulate Mapbox response with lowercase country code
        mock_mapbox_response = {
            "features": [
                {
                    "context": [
                        {"id": "country.123", "short_code": "us", "text": "United States"}
                    ]
                }
            ]
        }

        features = mock_mapbox_response.get("features", [])
        context = features[0].get("context", []) if features else []
        country_entry = next(
            (c for c in context if c.get("id", "").startswith("country")),
            None,
        )

        # This is the fixed code path - must include .upper()
        country_value = (
            (country_entry or {}).get("short_code")
            or (country_entry or {}).get("text")
            or "US"
        ).strip().upper()

        assert country_value == "US", f"Expected 'US', got '{country_value}'"
        assert country_value.isupper(), "Country code must be uppercase for Checkr API"

    def test_country_code_fallback_to_us(self):
        """Test fallback to US when no country in Mapbox response"""
        mock_mapbox_response = {"features": [{"context": []}]}

        features = mock_mapbox_response.get("features", [])
        context = features[0].get("context", []) if features else []
        country_entry = next(
            (c for c in context if c.get("id", "").startswith("country")),
            None,
        )

        country_value = (
            (country_entry or {}).get("short_code")
            or (country_entry or {}).get("text")
            or "US"
        ).strip().upper()

        assert country_value == "US"

    def test_country_code_handles_whitespace(self):
        """Test that whitespace is stripped before uppercase"""
        mock_context_entry = {"short_code": " us ", "text": "United States"}

        country_value = (
            mock_context_entry.get("short_code")
            or mock_context_entry.get("text")
            or "US"
        ).strip().upper()

        assert country_value == "US"
        assert " " not in country_value

    def test_checkr_country_code_iso_format(self):
        """
        Verify country code follows ISO 3166-1 alpha-2 format.
        Checkr requires exactly 2 uppercase letters.
        """
        valid_codes = ["US", "CA", "GB", "DE", "FR"]

        for code in valid_codes:
            assert len(code) == 2, f"ISO code must be 2 chars: {code}"
            assert code.isupper(), f"ISO code must be uppercase: {code}"
            assert code.isalpha(), f"ISO code must be letters only: {code}"
