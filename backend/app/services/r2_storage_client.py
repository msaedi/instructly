"""
R2StorageClient - Cloudflare R2 (S3-compatible) minimal client

Provides SigV4 presigned URL generation for GET/PUT/DELETE and helper methods
to upload/download bytes without requiring boto3.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import logging
from typing import Dict, Optional, Tuple

import requests

from ..core.config import settings

logger = logging.getLogger(__name__)


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


@dataclass
class PresignedUrl:
    url: str
    headers: Dict[str, str]
    expires_at: str


class R2StorageClient:
    """
    Minimal SigV4 signer for Cloudflare R2 requests.

    Note: Uses query-string authentication with UNSIGNED-PAYLOAD for simplicity.
    """

    def __init__(self) -> None:
        if (
            not settings.r2_bucket_name
            or not settings.r2_access_key_id
            or not settings.r2_secret_access_key
        ):
            raise RuntimeError("R2 configuration is missing; check r2_* settings")

        self.account_id = settings.r2_account_id
        self.access_key_id = settings.r2_access_key_id
        self.secret_key = settings.r2_secret_access_key.get_secret_value()
        self.bucket_name = settings.r2_bucket_name
        self.host = f"{self.account_id}.r2.cloudflarestorage.com"
        self.region = "auto"
        self.service = "s3"
        self.algorithm = "AWS4-HMAC-SHA256"

    def _build_presigned_url(
        self,
        method: str,
        object_key: str,
        expires_seconds: int,
        extra_query_params: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
    ) -> PresignedUrl:
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")

        canonical_uri = f"/{self.bucket_name}/{object_key}"
        signed_headers = "host"
        credential_scope = f"{datestamp}/{self.region}/{self.service}/aws4_request"

        params: Dict[str, str] = {
            "X-Amz-Algorithm": self.algorithm,
            "X-Amz-Credential": f"{self.access_key_id}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_seconds),
            "X-Amz-SignedHeaders": signed_headers,
            "X-Amz-Content-Sha256": "UNSIGNED-PAYLOAD",
        }
        if content_type:
            params["content-type"] = content_type
        if extra_query_params:
            params.update(extra_query_params)

        # Build canonical query string
        def qs(d: Dict[str, str]) -> str:
            from urllib.parse import quote

            parts: list[str] = []
            for k in sorted(d.keys()):
                parts.append(f"{quote(k, safe='-_.~')}={quote(str(d[k]), safe='-_.~')}")
            return "&".join(parts)

        canonical_querystring = qs(params)
        canonical_headers = f"host:{self.host}\n"
        canonical_request = "\n".join(
            [
                method.upper(),
                canonical_uri,
                canonical_querystring,
                canonical_headers,
                signed_headers,
                "UNSIGNED-PAYLOAD",
            ]
        )

        string_to_sign = "\n".join(
            [
                self.algorithm,
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )

        k_date = _hmac(("AWS4" + self.secret_key).encode("utf-8"), datestamp)
        k_region = _hmac(k_date, self.region)
        k_service = _hmac(k_region, self.service)
        k_signing = _hmac(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        signed_qs = canonical_querystring + f"&X-Amz-Signature={signature}"
        url = f"https://{self.host}{canonical_uri}?{signed_qs}"

        expires_at = now.replace(microsecond=0).isoformat()
        headers = {"Content-Type": content_type} if content_type else {}
        return PresignedUrl(url=url, headers=headers, expires_at=expires_at)

    def generate_presigned_put(
        self, object_key: str, content_type: str, expires_seconds: int = 300
    ) -> PresignedUrl:
        return self._build_presigned_url(
            "PUT", object_key, expires_seconds, content_type=content_type
        )

    def generate_presigned_get(self, object_key: str, expires_seconds: int = 3600) -> PresignedUrl:
        return self._build_presigned_url("GET", object_key, expires_seconds)

    def generate_presigned_delete(
        self, object_key: str, expires_seconds: int = 300
    ) -> PresignedUrl:
        return self._build_presigned_url("DELETE", object_key, expires_seconds)

    # Convenience helpers
    def upload_bytes(
        self, object_key: str, data: bytes, content_type: str
    ) -> Tuple[bool, Optional[int]]:
        try:
            pre = self.generate_presigned_put(object_key, content_type)
            resp = requests.put(pre.url, data=data, headers=pre.headers, timeout=30)
            return (200 <= resp.status_code < 300, resp.status_code)
        except Exception as e:
            logger.error(f"Failed to upload {object_key}: {e}")
            return (False, None)

    def download_bytes(self, object_key: str) -> Optional[bytes]:
        try:
            pre = self.generate_presigned_get(object_key)
            resp = requests.get(pre.url, timeout=30)
            if 200 <= resp.status_code < 300:
                return resp.content
            logger.error(f"Failed to download {object_key}: status={resp.status_code}")
            return None
        except Exception as e:
            logger.error(f"Failed to download {object_key}: {e}")
            return None

    def delete_object(self, object_key: str) -> bool:
        try:
            pre = self.generate_presigned_delete(object_key)
            resp = requests.delete(pre.url, timeout=30)
            return 200 <= resp.status_code < 300 or resp.status_code == 404
        except Exception as e:
            logger.error(f"Failed to delete {object_key}: {e}")
            return False
