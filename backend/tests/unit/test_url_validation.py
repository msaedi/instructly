# backend/tests/unit/test_url_validation.py
"""Tests for shared URL validation utility."""


from app.utils.url_validation import is_allowed_origin, origin_from_header


class TestIsAllowedOrigin:
    """Tests for is_allowed_origin()."""

    # Local development - should allow
    def test_localhost_allowed(self):
        assert is_allowed_origin("http://localhost:3000") is True
        assert is_allowed_origin("http://localhost") is True
        assert is_allowed_origin("https://localhost:3000") is True

    def test_127_0_0_1_allowed(self):
        assert is_allowed_origin("http://127.0.0.1:3000") is True
        assert is_allowed_origin("http://127.0.0.1") is True

    def test_beta_local_allowed(self):
        assert is_allowed_origin("http://beta-local.instainstru.com:3000") is True
        assert is_allowed_origin("https://beta-local.instainstru.com:3000") is True

    # Random IPs - should reject (security fix)
    def test_random_ips_rejected(self):
        assert is_allowed_origin("http://192.168.1.1:3000") is False
        assert is_allowed_origin("http://1.2.3.4:3000") is False
        assert is_allowed_origin("http://10.0.0.1:3000") is False
        assert is_allowed_origin("http://8.8.8.8") is False

    # Production domains - require HTTPS
    def test_production_domains_require_https(self):
        assert is_allowed_origin("https://instainstru.com") is True
        assert is_allowed_origin("http://instainstru.com") is False  # HTTP rejected

    def test_www_domain_allowed(self):
        assert is_allowed_origin("https://www.instainstru.com") is True
        assert is_allowed_origin("http://www.instainstru.com") is False

    def test_subdomains_allowed_with_https(self):
        assert is_allowed_origin("https://beta.instainstru.com") is True
        assert is_allowed_origin("https://preview.instainstru.com") is True
        assert is_allowed_origin("http://beta.instainstru.com") is False  # HTTP rejected

    # Invalid inputs
    def test_none_rejected(self):
        assert is_allowed_origin(None) is False

    def test_empty_string_rejected(self):
        assert is_allowed_origin("") is False

    def test_malformed_url_rejected(self):
        assert is_allowed_origin("not-a-url") is False
        assert is_allowed_origin("://missing-scheme.com") is False

    # Malicious inputs - security
    def test_similar_domains_rejected(self):
        """Prevent typosquatting/phishing domains."""
        assert is_allowed_origin("https://instainstru.com.evil.com") is False
        assert is_allowed_origin("https://fake-instainstru.com") is False
        assert is_allowed_origin("https://instainstru.evil.com") is False


class TestOriginFromHeader:
    """Tests for origin_from_header() extraction."""

    def test_extracts_origin_from_valid_url(self):
        result = origin_from_header("https://beta.instainstru.com")
        assert result == "https://beta.instainstru.com"

    def test_extracts_origin_from_full_url_with_path(self):
        """Should extract just origin, stripping path."""
        result = origin_from_header("https://preview.instainstru.com/page/subpage")
        assert result == "https://preview.instainstru.com"

    def test_extracts_origin_with_port(self):
        result = origin_from_header("http://localhost:3000/some/path")
        assert result == "http://localhost:3000"

    def test_strips_trailing_slash(self):
        result = origin_from_header("https://beta.instainstru.com/")
        assert result == "https://beta.instainstru.com"

    def test_returns_none_for_none_input(self):
        result = origin_from_header(None)
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = origin_from_header("")
        assert result is None

    def test_returns_none_for_invalid_scheme(self):
        result = origin_from_header("ftp://example.com")
        assert result is None

    def test_returns_none_for_malformed_url(self):
        result = origin_from_header("not-a-url")
        assert result is None

    def test_http_scheme_allowed(self):
        result = origin_from_header("http://localhost:3000")
        assert result == "http://localhost:3000"

    def test_https_scheme_allowed(self):
        result = origin_from_header("https://example.com")
        assert result == "https://example.com"
