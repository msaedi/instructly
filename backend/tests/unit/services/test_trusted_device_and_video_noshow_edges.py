"""
Unit tests for coverage gaps in:
  - trusted_device_service.py (lines 57, 59, 71, 73, 77, 79, 164, 180, 184, 188)
  - video_tasks.py (lines 93-102, 147-148)

Covers:
  - parse_user_agent: Edge, Opera browsers; iPad, Android, Windows, Linux OS detection
  - revoke_device_for_user: device not found / wrong user returns None
  - current_cookie_matches_device: no cookie / device not found returns False
  - delete_expired_devices: delegates to repository
  - _get_scheduled_end_utc: fallback from start+duration, missing data returns None
  - detect_video_no_shows: skips bookings before scheduled end
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.trusted_device_service import TrustedDeviceService
from app.tasks.video_tasks import _get_scheduled_end_utc

# ---------------------------------------------------------------------------
# TrustedDeviceService — parse_user_agent browser detection
# ---------------------------------------------------------------------------

class TestParseUserAgentBrowser:
    """Cover browser detection branches in parse_user_agent."""

    @pytest.mark.unit
    def test_edge_browser_via_edg(self) -> None:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/120.0.0.0"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.browser_family == "Edge"

    @pytest.mark.unit
    def test_edge_browser_via_edge_slash(self) -> None:
        ua = "Mozilla/5.0 (Windows NT 10.0) Edge/18.17763"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.browser_family == "Edge"

    @pytest.mark.unit
    def test_opera_browser_via_opr(self) -> None:
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 OPR/105.0.0.0"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.browser_family == "Opera"

    @pytest.mark.unit
    def test_opera_browser_via_opera(self) -> None:
        ua = "Opera/9.80 (Windows NT 6.1; WOW64) Presto/2.12.388"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.browser_family == "Opera"


# ---------------------------------------------------------------------------
# TrustedDeviceService — parse_user_agent OS detection
# ---------------------------------------------------------------------------

class TestParseUserAgentOS:
    """Cover OS detection branches in parse_user_agent."""

    @pytest.mark.unit
    def test_ipad_os(self) -> None:
        ua = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.os_family == "iPad"

    @pytest.mark.unit
    def test_android_os(self) -> None:
        ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.os_family == "Android"

    @pytest.mark.unit
    def test_windows_os(self) -> None:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.os_family == "Windows"

    @pytest.mark.unit
    def test_linux_os(self) -> None:
        ua = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.os_family == "Linux"

    @pytest.mark.unit
    def test_linux_os_via_x11(self) -> None:
        ua = "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.os_family == "Linux"

    @pytest.mark.unit
    def test_device_name_combines_browser_and_os(self) -> None:
        ua = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) OPR/105.0"
        sig = TrustedDeviceService.parse_user_agent(ua)
        assert sig.device_name == "Opera on iPad"


# ---------------------------------------------------------------------------
# TrustedDeviceService — revoke_device_for_user
# ---------------------------------------------------------------------------

class TestRevokeDeviceForUser:
    """Cover lines 162-164: device not found or wrong user returns None."""

    @pytest.mark.unit
    def test_revoke_device_not_found(self) -> None:
        mock_db = MagicMock()
        with patch(
            "app.services.trusted_device_service.RepositoryFactory"
        ) as mock_factory:
            mock_repo = MagicMock()
            mock_factory.create_trusted_device_repository.return_value = mock_repo
            mock_repo.get_by_id.return_value = None

            svc = TrustedDeviceService(mock_db)
            result = svc.revoke_device_for_user(
                user_id="01USERAAAAAAAAAAAAAAAAAAA1",
                device_id="01DEVICEAAAAAAAAAAAAAAAAAA",
            )

        assert result is None
        mock_repo.delete.assert_not_called()

    @pytest.mark.unit
    def test_revoke_device_wrong_user(self) -> None:
        mock_db = MagicMock()
        with patch(
            "app.services.trusted_device_service.RepositoryFactory"
        ) as mock_factory:
            mock_repo = MagicMock()
            mock_factory.create_trusted_device_repository.return_value = mock_repo

            device = MagicMock()
            device.user_id = "01USEROTTTTTTTTTTTTTTTTTT1"  # different user
            mock_repo.get_by_id.return_value = device

            svc = TrustedDeviceService(mock_db)
            result = svc.revoke_device_for_user(
                user_id="01USERAAAAAAAAAAAAAAAAAAA1",
                device_id="01DEVICEAAAAAAAAAAAAAAAAAA",
            )

        assert result is None
        mock_repo.delete.assert_not_called()


# ---------------------------------------------------------------------------
# TrustedDeviceService — current_cookie_matches_device
# ---------------------------------------------------------------------------

class TestCurrentCookieMatchesDevice:
    """Cover lines 180 and 184: no cookie or device not found returns False."""

    @pytest.mark.unit
    def test_no_cookie_returns_false(self) -> None:
        mock_db = MagicMock()
        with patch(
            "app.services.trusted_device_service.RepositoryFactory"
        ) as mock_factory:
            mock_repo = MagicMock()
            mock_factory.create_trusted_device_repository.return_value = mock_repo

            svc = TrustedDeviceService(mock_db)

            request = MagicMock()
            request.cookies = {}  # no trust cookie

            result = svc.current_cookie_matches_device(
                user_id="01USERAAAAAAAAAAAAAAAAAAA1",
                device_id="01DEVICEAAAAAAAAAAAAAAAAAA",
                request=request,
            )

        assert result is False
        mock_repo.find_by_token_hash.assert_not_called()

    @pytest.mark.unit
    def test_device_not_found_returns_false(self) -> None:
        mock_db = MagicMock()
        with patch(
            "app.services.trusted_device_service.RepositoryFactory"
        ) as mock_factory:
            mock_repo = MagicMock()
            mock_factory.create_trusted_device_repository.return_value = mock_repo
            mock_repo.find_by_token_hash.return_value = None

            svc = TrustedDeviceService(mock_db)

            request = MagicMock()
            request.cookies = {"tfa_device_trust": "some-token-value"}

            result = svc.current_cookie_matches_device(
                user_id="01USERAAAAAAAAAAAAAAAAAAA1",
                device_id="01DEVICEAAAAAAAAAAAAAAAAAA",
                request=request,
            )

        assert result is False
        mock_repo.find_by_token_hash.assert_called_once()


# ---------------------------------------------------------------------------
# TrustedDeviceService — delete_expired_devices
# ---------------------------------------------------------------------------

class TestDeleteExpiredDevices:
    """Cover line 188: delegates to repository.delete_expired()."""

    @pytest.mark.unit
    def test_delete_expired_delegates(self) -> None:
        mock_db = MagicMock()
        with patch(
            "app.services.trusted_device_service.RepositoryFactory"
        ) as mock_factory:
            mock_repo = MagicMock()
            mock_factory.create_trusted_device_repository.return_value = mock_repo
            mock_repo.delete_expired.return_value = 5

            svc = TrustedDeviceService(mock_db)
            result = svc.delete_expired_devices()

        assert result == 5
        mock_repo.delete_expired.assert_called_once()


# ---------------------------------------------------------------------------
# video_tasks — _get_scheduled_end_utc
# ---------------------------------------------------------------------------

class TestGetScheduledEndUtc:
    """Cover lines 93-102: fallback computation and None returns."""

    @pytest.mark.unit
    def test_from_start_and_duration(self) -> None:
        start = datetime(2026, 4, 3, 14, 0, 0, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            booking_end_utc=None,
            booking_start_utc=start,
            duration_minutes=60,
        )
        result = _get_scheduled_end_utc(booking)
        assert result == start + timedelta(minutes=60)

    @pytest.mark.unit
    def test_from_start_and_float_duration(self) -> None:
        start = datetime(2026, 4, 3, 14, 0, 0, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            booking_end_utc=None,
            booking_start_utc=start,
            duration_minutes=45.5,
        )
        result = _get_scheduled_end_utc(booking)
        assert result == start + timedelta(minutes=45.5)

    @pytest.mark.unit
    def test_missing_start_returns_none(self) -> None:
        booking = SimpleNamespace(
            booking_end_utc=None,
            booking_start_utc=None,
            duration_minutes=60,
        )
        result = _get_scheduled_end_utc(booking)
        assert result is None

    @pytest.mark.unit
    def test_zero_duration_returns_none(self) -> None:
        start = datetime(2026, 4, 3, 14, 0, 0, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            booking_end_utc=None,
            booking_start_utc=start,
            duration_minutes=0,
        )
        result = _get_scheduled_end_utc(booking)
        assert result is None

    @pytest.mark.unit
    def test_non_numeric_duration_returns_none(self) -> None:
        start = datetime(2026, 4, 3, 14, 0, 0, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            booking_end_utc=None,
            booking_start_utc=start,
            duration_minutes="sixty",
        )
        result = _get_scheduled_end_utc(booking)
        assert result is None

    @pytest.mark.unit
    def test_missing_all_attributes_returns_none(self) -> None:
        """Booking object with none of the relevant attributes."""
        booking = SimpleNamespace()
        result = _get_scheduled_end_utc(booking)
        assert result is None

    @pytest.mark.unit
    def test_negative_duration_returns_none(self) -> None:
        start = datetime(2026, 4, 3, 14, 0, 0, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            booking_end_utc=None,
            booking_start_utc=start,
            duration_minutes=-30,
        )
        result = _get_scheduled_end_utc(booking)
        assert result is None


# ---------------------------------------------------------------------------
# video_tasks — detect_video_no_shows skips before scheduled end
# ---------------------------------------------------------------------------

class TestDetectNoShowsSkipsBeforeEnd:
    """Cover lines 147-148: bookings skipped when now < scheduled_end_utc."""

    @pytest.mark.unit
    def test_skips_booking_before_scheduled_end(self) -> None:
        """scheduled_end_utc is in the future relative to now -> skipped."""
        now = datetime(2026, 4, 3, 15, 0, 0, tzinfo=timezone.utc)
        future_end = now + timedelta(hours=1)

        booking = MagicMock()
        booking.id = "01BOOKINGAAAAAAAAAAAAAAAAAA"

        video_session = MagicMock()

        mock_db = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_video_no_show_candidates.return_value = [
            (booking, video_session),
        ]

        mock_booking_service = MagicMock()

        with (
            patch("app.tasks.video_tasks.settings") as mock_settings,
            patch("app.tasks.video_tasks.get_db") as mock_get_db,
            patch("app.tasks.video_tasks.RepositoryFactory") as mock_rf,
            patch("app.tasks.video_tasks.BookingService") as mock_bs_cls,
            patch(
                "app.tasks.video_tasks._get_scheduled_end_utc",
                return_value=future_end,
            ),
        ):
            mock_settings.hundredms_enabled = True
            mock_get_db.return_value = iter([mock_db])
            mock_rf.create_booking_repository.return_value = mock_booking_repo
            mock_bs_cls.return_value = mock_booking_service

            from app.tasks.video_tasks import detect_video_no_shows

            result = detect_video_no_shows()

        assert result["processed"] == 1
        assert result["skipped"] == 1
        assert result["reported"] == 0
        mock_booking_service.report_automated_no_show.assert_not_called()

    @pytest.mark.unit
    def test_skips_booking_with_none_scheduled_end(self) -> None:
        """When _get_scheduled_end_utc returns None, the booking is skipped."""
        booking = MagicMock()
        booking.id = "01BOOKINGAAAAAAAAAAAAAAAAAA"

        video_session = MagicMock()

        mock_db = MagicMock()
        mock_booking_repo = MagicMock()
        mock_booking_repo.get_video_no_show_candidates.return_value = [
            (booking, video_session),
        ]

        mock_booking_service = MagicMock()

        with (
            patch("app.tasks.video_tasks.settings") as mock_settings,
            patch("app.tasks.video_tasks.get_db") as mock_get_db,
            patch("app.tasks.video_tasks.RepositoryFactory") as mock_rf,
            patch("app.tasks.video_tasks.BookingService") as mock_bs_cls,
            patch(
                "app.tasks.video_tasks._get_scheduled_end_utc",
                return_value=None,
            ),
        ):
            mock_settings.hundredms_enabled = True
            mock_get_db.return_value = iter([mock_db])
            mock_rf.create_booking_repository.return_value = mock_booking_repo
            mock_bs_cls.return_value = mock_booking_service

            from app.tasks.video_tasks import detect_video_no_shows

            result = detect_video_no_shows()

        assert result["processed"] == 1
        assert result["skipped"] == 1
        assert result["reported"] == 0
