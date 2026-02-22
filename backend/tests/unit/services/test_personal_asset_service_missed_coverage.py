"""Tests targeting missed lines in app/services/personal_asset_service.py.

Missed lines:
  97->104: _build_storage when R2 is configured but R2StorageClient() raises
  170->183: _get_presigned_view_for_user cache miss, no presigned URL
  191: _get_presigned_view_for_user when pre is None (returned by limits)
  194-195: profile_pic_url_cache_misses_total.labels raises
  196->205: cache miss, sets URL in cache
  216-217: finalize_profile_picture when upload returns False (not in test mode)
  264-265: finalize_profile_picture: cache.delete_pattern raises
  292->297: delete_profile_picture: cache.delete_pattern raises
  321->326: delete_profile_picture: updated is None
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.personal_asset_service import (
    PersonalAssetService,
)


class TestPersonalAssetServiceMissedLines:
    """Test missed lines in PersonalAssetService."""

    def _make_service(self, storage=None, cache=None, users_repo=None, images=None):
        mock_db = MagicMock()
        return PersonalAssetService(
            db=mock_db,
            storage=storage or MagicMock(),
            images=images or MagicMock(),
            users_repo=users_repo or MagicMock(),
            cache_service=cache,
        )

    def test_build_storage_r2_configured_but_constructor_fails(self) -> None:
        """Lines 97->104: R2 configured but constructor raises."""
        import app.services.personal_asset_service as mod

        original = mod._FALLBACK_STORAGE_WARNED
        mod._FALLBACK_STORAGE_WARNED = False
        try:
            with patch.object(mod, "_is_r2_storage_configured", return_value=True), \
                 patch.object(mod, "R2StorageClient", side_effect=RuntimeError("bad config")):
                mock_db = MagicMock()
                svc = PersonalAssetService(db=mock_db, images=MagicMock(), users_repo=MagicMock())
                # Should fall back to NullStorageClient
                from app.services.storage_null_client import NullStorageClient
                assert isinstance(svc.storage, NullStorageClient)
        finally:
            mod._FALLBACK_STORAGE_WARNED = original

    def test_get_presigned_view_cache_miss_presign_returns_none(self) -> None:
        """Lines 170->183, 191: cache miss + _generate_presigned_with_limits returns None."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # cache miss

        svc = self._make_service(cache=mock_cache)

        with patch.object(svc, "_generate_presigned_with_limits", return_value=None):
            result = svc._get_presigned_view_for_user("user1", 1, "display")

        assert result is None

    def test_get_presigned_view_cache_miss_successful(self) -> None:
        """Lines 196->205: cache miss, presign succeeds, caches the URL."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # cache miss

        mock_presigned = MagicMock()
        mock_presigned.url = "https://example.com/signed"
        mock_presigned.expires_at = "2025-01-01T00:00:00Z"

        svc = self._make_service(cache=mock_cache)

        with patch.object(svc, "_generate_presigned_with_limits", return_value=mock_presigned), \
             patch("app.services.personal_asset_service.profile_pic_url_cache_misses_total") as mock_counter:
            mock_counter.labels.return_value.inc = MagicMock()
            result = svc._get_presigned_view_for_user("user1", 1, "display")

        assert result is not None
        assert result.url == "https://example.com/signed"
        mock_cache.set.assert_called_once()

    def test_get_presigned_view_cache_misses_counter_raises(self) -> None:
        """Lines 194-195: profile_pic_url_cache_misses_total.labels raises exception."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        mock_presigned = MagicMock()
        mock_presigned.url = "https://example.com/signed"
        mock_presigned.expires_at = "2025-01-01T00:00:00Z"

        svc = self._make_service(cache=mock_cache)

        with patch.object(svc, "_generate_presigned_with_limits", return_value=mock_presigned), \
             patch("app.services.personal_asset_service.profile_pic_url_cache_misses_total") as mock_counter:
            mock_counter.labels.side_effect = RuntimeError("prometheus fail")
            result = svc._get_presigned_view_for_user("user1", 1, "display")

        # Should still return the presigned view despite counter error
        assert result is not None
        assert result.url == "https://example.com/signed"

    def test_finalize_profile_picture_cache_delete_pattern_fails(self) -> None:
        """Lines 264-265: cache.delete_pattern raises during finalize."""
        mock_cache = MagicMock()
        mock_cache.delete_pattern.side_effect = RuntimeError("cache error")
        mock_storage = MagicMock()
        mock_storage.download_bytes.return_value = b"fake_image_data"
        mock_storage.upload_bytes.return_value = (True, "key")
        mock_storage.delete_object.return_value = None
        mock_images = MagicMock()
        mock_images.process_profile_picture.return_value = MagicMock(
            original=b"orig", display_400=b"disp", thumb_200=b"thumb"
        )
        mock_users = MagicMock()
        mock_users.update_profile.return_value = MagicMock()

        svc = self._make_service(
            storage=mock_storage, cache=mock_cache, users_repo=mock_users, images=mock_images
        )

        mock_user = MagicMock()
        mock_user.id = "user1"
        mock_user.profile_picture_version = 1

        # Should not raise despite cache error
        result = svc.finalize_profile_picture(mock_user, "temp/key.jpg")
        assert result is True

    def test_delete_profile_picture_cache_delete_pattern_fails(self) -> None:
        """Lines 292->297: cache.delete_pattern raises during delete."""
        mock_cache = MagicMock()
        mock_cache.delete_pattern.side_effect = RuntimeError("cache error")
        mock_storage = MagicMock()
        mock_storage.delete_object.return_value = None
        mock_users = MagicMock()
        mock_users.update_profile.return_value = MagicMock()

        svc = self._make_service(storage=mock_storage, cache=mock_cache, users_repo=mock_users)

        mock_user = MagicMock()
        mock_user.id = "user1"
        mock_user.profile_picture_version = 1

        # Should not raise despite cache error
        result = svc.delete_profile_picture(mock_user)
        assert result is True

    def test_delete_profile_picture_update_returns_none(self) -> None:
        """Lines 321->326: update_profile returns None => returns False."""
        mock_storage = MagicMock()
        mock_storage.delete_object.return_value = None
        mock_users = MagicMock()
        mock_users.update_profile.return_value = None  # returns None

        svc = self._make_service(storage=mock_storage, users_repo=mock_users)

        mock_user = MagicMock()
        mock_user.id = "user1"
        mock_user.profile_picture_version = 1

        result = svc.delete_profile_picture(mock_user)
        assert result is False

    def test_get_presigned_view_variant_original(self) -> None:
        """Coverage: variant='original' branch in _get_presigned_view_for_user."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        mock_presigned = MagicMock()
        mock_presigned.url = "https://example.com/original"
        mock_presigned.expires_at = "2025-01-01T00:00:00Z"

        svc = self._make_service(cache=mock_cache)

        with patch.object(svc, "_generate_presigned_with_limits", return_value=mock_presigned), \
             patch("app.services.personal_asset_service.profile_pic_url_cache_misses_total") as mock_counter:
            mock_counter.labels.return_value.inc = MagicMock()
            result = svc._get_presigned_view_for_user("user1", 1, "original")

        assert result is not None
        assert result.url == "https://example.com/original"

    def test_get_presigned_view_variant_thumb(self) -> None:
        """Coverage: variant='thumb' branch in _get_presigned_view_for_user."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        mock_presigned = MagicMock()
        mock_presigned.url = "https://example.com/thumb"
        mock_presigned.expires_at = "2025-01-01T00:00:00Z"

        svc = self._make_service(cache=mock_cache)

        with patch.object(svc, "_generate_presigned_with_limits", return_value=mock_presigned), \
             patch("app.services.personal_asset_service.profile_pic_url_cache_misses_total") as mock_counter:
            mock_counter.labels.return_value.inc = MagicMock()
            result = svc._get_presigned_view_for_user("user1", 1, "thumb")

        assert result is not None
