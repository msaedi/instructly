"""Redis-backed idempotency tracking for MCP write operations."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import ServiceException
from app.services.base import BaseService


class MCPIdempotencyService(BaseService):
    """
    Tracks idempotency keys for MCP write operations.
    Keys are stored for 24 hours.
    """

    TTL_SECONDS = 60 * 60 * 24

    def __init__(self, db: Session, redis_client: Optional[Any] = None):
        super().__init__(db)
        self._redis = redis_client
        self._operation_context: str | None = None

    @BaseService.measure_operation("mcp_idempotency.check_and_store")
    async def check_and_store(
        self, idempotency_key: str, operation: str
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Check if key exists. If yes, return (True, cached_result).
        If no, store key and return (False, None).
        """
        self._operation_context = operation
        redis = await self._get_redis()
        storage_key = self._key(operation, idempotency_key)
        cached_raw = await redis.get(storage_key)
        if cached_raw:
            cached = self._safe_load(cached_raw)
            if isinstance(cached, dict) and cached.get("status") == "pending":
                return True, None
            return True, cached

        pending_payload = json.dumps({"status": "pending"})
        was_set = await redis.set(storage_key, pending_payload, ex=self.TTL_SECONDS, nx=True)
        if not was_set:
            cached_raw = await redis.get(storage_key)
            cached = self._safe_load(cached_raw) if cached_raw else None
            if isinstance(cached, dict) and cached.get("status") == "pending":
                return True, None
            return True, cached

        return False, None

    @BaseService.measure_operation("mcp_idempotency.store_result")
    async def store_result(self, idempotency_key: str, result: dict[str, Any]) -> None:
        """Store the result for a completed operation."""
        operation = self._operation_context
        if not operation:
            raise ServiceException(
                "Idempotency operation context missing", code="mcp_idem_operation_missing"
            )
        redis = await self._get_redis()
        storage_key = self._key(operation, idempotency_key)
        await redis.setex(storage_key, self.TTL_SECONDS, json.dumps(result))

    def _key(self, operation: str, key: str) -> str:
        return f"mcp:idempotency:{operation}:{key}"

    async def _get_redis(self) -> Any:
        if self._redis is not None:
            return self._redis
        from app.ratelimit.redis_backend import get_redis

        return await get_redis()

    @staticmethod
    def _safe_load(raw: Any) -> dict[str, Any] | None:
        try:
            decoded = json.loads(raw)
        except Exception:
            return None
        if not isinstance(decoded, dict):
            return None
        return decoded
