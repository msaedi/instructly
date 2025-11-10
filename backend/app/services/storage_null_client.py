from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .r2_storage_client import PresignedUrl


class NullStorageClient:
    """No-op storage client used when Cloudflare R2 is not configured."""

    def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D401
        self._label = "null-storage"

    def _placeholder_presigned(self) -> PresignedUrl:
        expires = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return PresignedUrl(url="", headers={}, expires_at=expires)

    def generate_presigned_put(
        self, object_key: str, content_type: str, expires_seconds: int = 300
    ) -> PresignedUrl:
        return self._placeholder_presigned()

    def generate_presigned_get(self, object_key: str, expires_seconds: int = 3600) -> PresignedUrl:
        return self._placeholder_presigned()

    def generate_presigned_delete(
        self, object_key: str, expires_seconds: int = 300
    ) -> PresignedUrl:
        return self._placeholder_presigned()

    def upload_bytes(
        self, object_key: str, data: bytes, content_type: str
    ) -> Tuple[bool, Optional[int]]:
        return True, None

    def download_bytes(self, object_key: str) -> Optional[bytes]:
        return None

    def delete_object(self, object_key: str) -> bool:
        return True

    def list_objects(self, prefix: Optional[str] = None) -> List[str]:
        return []
