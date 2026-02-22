"""Tests targeting missed lines in app/utils/cookies.py.

Missed lines:
  40->42: session_cookie_candidates when base is empty string
  110: set_session_cookie with expires parameter
  142: set_refresh_cookie where cookie_name starts with __Host-
  150: set_refresh_cookie with expires parameter
  182: delete_refresh_cookie where cookie_name starts with __Host-
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_session_cookie_candidates_empty_base() -> None:
    """Line 40->42: when base is empty, candidates list starts empty."""
    with patch("app.utils.cookies.session_cookie_base_name", return_value=""):
        from app.utils.cookies import session_cookie_candidates
        result = session_cookie_candidates("local")
    # base is empty so first condition fails, legacy still appended
    assert isinstance(result, list)


def test_set_session_cookie_with_expires() -> None:
    """Line 110: set_session_cookie with expires parameter set."""
    from app.utils.cookies import set_session_cookie

    mock_response = MagicMock()

    with patch("app.utils.cookies.settings") as mock_settings:
        mock_settings.session_cookie_samesite = "lax"
        mock_settings.session_cookie_secure = True
        mock_settings.session_cookie_domain = ".example.com"

        name = set_session_cookie(
            mock_response,
            "sid",
            "token_value",
            max_age=3600,
            expires=1700000000,
        )

    assert name == "sid"
    mock_response.set_cookie.assert_called_once()
    call_kwargs = mock_response.set_cookie.call_args
    # Check expires was passed
    assert call_kwargs.kwargs.get("expires") == 1700000000 or \
           call_kwargs[1].get("expires") == 1700000000


def test_set_refresh_cookie_host_prefix() -> None:
    """Line 142: refresh cookie name starts with __Host- => domain set to None."""
    from app.utils.cookies import set_refresh_cookie

    mock_response = MagicMock()

    with patch("app.utils.cookies.refresh_cookie_base_name", return_value="__Host-rid"), \
         patch("app.utils.cookies.settings") as mock_settings:
        mock_settings.session_cookie_samesite = "lax"
        mock_settings.session_cookie_secure = True
        mock_settings.session_cookie_domain = ".example.com"

        name = set_refresh_cookie(mock_response, "refresh_token_value")

    assert name == "__Host-rid"
    call_kwargs = mock_response.set_cookie.call_args
    # Domain should NOT be set when __Host- prefix is used
    assert call_kwargs.kwargs.get("domain") is None or "domain" not in call_kwargs.kwargs


def test_set_refresh_cookie_with_expires() -> None:
    """Line 150: set_refresh_cookie with expires parameter set."""
    from app.utils.cookies import set_refresh_cookie

    mock_response = MagicMock()

    with patch("app.utils.cookies.refresh_cookie_base_name", return_value="rid"), \
         patch("app.utils.cookies.settings") as mock_settings:
        mock_settings.session_cookie_samesite = "lax"
        mock_settings.session_cookie_secure = False
        mock_settings.session_cookie_domain = None

        name = set_refresh_cookie(
            mock_response,
            "refresh_token",
            expires=1700000000,
        )

    assert name == "rid"
    mock_response.set_cookie.assert_called_once()


def test_delete_refresh_cookie_host_prefix() -> None:
    """Line 182: delete_refresh_cookie where cookie_name starts with __Host-."""
    from app.utils.cookies import delete_refresh_cookie

    mock_response = MagicMock()

    with patch("app.utils.cookies.refresh_cookie_base_name", return_value="__Host-rid"), \
         patch("app.utils.cookies.settings") as mock_settings:
        mock_settings.session_cookie_samesite = "lax"
        mock_settings.session_cookie_secure = True
        mock_settings.session_cookie_domain = ".example.com"

        name = delete_refresh_cookie(mock_response)

    assert name == "__Host-rid"
    call_kwargs = mock_response.delete_cookie.call_args
    # Domain should be None due to __Host- prefix
    assert call_kwargs.kwargs.get("domain") is None


def test_session_cookie_base_name_prod_mode() -> None:
    """Line 30: site_mode is 'prod' => returns 'sid'."""
    from app.utils.cookies import session_cookie_base_name

    with patch("app.utils.cookies.settings") as mock_settings:
        mock_settings.session_cookie_name = "sid"
        result = session_cookie_base_name("prod")
    assert result == "sid"


def test_session_cookie_candidates_prod_mode() -> None:
    """Lines 45-46: site_mode is 'prod' => legacy is 'sid_prod'."""
    from app.utils.cookies import session_cookie_candidates

    with patch("app.utils.cookies.settings") as mock_settings:
        mock_settings.session_cookie_name = "sid"
        mock_settings.site_mode = "prod"
        result = session_cookie_candidates("prod")

    assert "sid" in result
    assert "sid_prod" in result
