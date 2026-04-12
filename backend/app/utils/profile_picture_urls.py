"""Helpers for building signed profile picture URLs."""

from __future__ import annotations

import logging
import re
from typing import Literal, Optional

from app.services.r2_storage_client import R2StorageClient

logger = logging.getLogger(__name__)


_PROFILE_PICTURE_VERSION_RE = re.compile(r"/v(?P<version>\d+)/")


def _profile_picture_variant_key(
    key: str,
    variant: Literal["original", "display", "thumb"],
) -> str:
    if variant == "original":
        return key

    if key.endswith("/original.jpg"):
        suffix = "display_400x400.jpg" if variant == "display" else "thumb_200x200.jpg"
        return f"{key[:-len('original.jpg')]}{suffix}"

    return key


def _profile_picture_version_from_key(key: str) -> Optional[int]:
    if not isinstance(key, str) or not key:
        return None
    match = _PROFILE_PICTURE_VERSION_RE.search(key)
    if not match:
        return None
    try:
        version = int(match.group("version"))
    except (TypeError, ValueError):
        return None
    return version if version > 0 else None


def build_photo_url(
    key: Optional[str],
    *,
    version: Optional[int] = None,
    variant: Literal["original", "display", "thumb"] = "original",
) -> Optional[str]:
    """Build a signed profile picture URL for a stored asset key."""
    if not isinstance(key, str):
        return None
    normalized_key = key.strip()
    if not normalized_key:
        return None

    resolved_version = (
        version
        if isinstance(version, int) and version > 0
        else _profile_picture_version_from_key(normalized_key)
    )
    object_key = _profile_picture_variant_key(normalized_key, variant)
    extra_query_params = {"v": str(resolved_version)} if resolved_version is not None else None

    try:
        # R2StorageClient is a lightweight in-process signer: construction only reads
        # settings and derives request metadata, so creating it per call does not open
        # network sessions or connection pools.
        presigned = R2StorageClient().generate_presigned_get(
            object_key,
            # 24h matches the existing UserAvatar presign TTL for cards. Cache busting
            # on photo updates is handled by the v= query param, so longer TTL doesn't
            # cause staleness.
            expires_seconds=86400,
            extra_query_params=extra_query_params,
        )
    except Exception:
        logger.warning(
            "Failed to build signed profile picture URL",
            extra={"object_key": object_key, "variant": variant},
            exc_info=True,
        )
        return None

    return presigned.url or None
