"""
Tier 5: LLM-based location resolution.

Use GPT to interpret complex/semantic location strings (e.g., landmarks),
mapping them onto known `region_boundaries.region_name` values.

This is intentionally the last-resort tier due to latency and cost.
Uses strict timeouts to fail fast under load (no retries).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, OpenAIError

from app.core.config import settings
from app.services.search.config import get_search_config
from app.services.search.openai_semaphore import OPENAI_CALL_SEMAPHORE

logger = logging.getLogger(__name__)

# Strict OpenAI timeouts for async calls.
# Fail fast rather than block the event loop with retries.
DEFAULT_LOCATION_TIMEOUT_MS = int(getattr(settings, "openai_location_timeout_ms", 3000))


_SYSTEM_PROMPT_TEMPLATE = """You resolve NYC location queries to known NYC neighborhoods.

Given a user's location query, pick the closest matching neighborhood(s) from the allowed list.

Rules:
- Return ONLY neighborhood names from the allowed list (exact string match).
- If the query is a landmark (e.g., "museum mile"), map it to the nearest neighborhood(s).
- If ambiguous, return multiple plausible neighborhoods (max 5).
- If you cannot map it confidently, return an empty list.

Allowed neighborhood names:
{neighborhoods}

Respond with JSON only:
{{
  "neighborhoods": ["Neighborhood Name 1", "Neighborhood Name 2"],
  "confidence": 0.0,
  "reason": "short reason"
}}
"""


class LocationLLMService:
    """LLM helper to map freeform location text to region_boundaries names."""

    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None
        self._client_max_retries: Optional[int] = None
        self._client_timeout_s: Optional[float] = None

    @staticmethod
    def _coerce_max_retries(value: Any) -> int:
        try:
            max_retries = int(value)
        except (TypeError, ValueError):
            max_retries = 2
        return max(0, max_retries)

    @property
    def client(self) -> AsyncOpenAI:
        max_retries = self._coerce_max_retries(getattr(get_search_config(), "max_retries", 2))
        config = get_search_config()
        timeout_s = max(0.0, float(config.location_timeout_ms) / 1000.0)
        if self._client is None:
            self._client = AsyncOpenAI(
                timeout=timeout_s,
                max_retries=max_retries,
            )
            self._client_max_retries = max_retries
            self._client_timeout_s = timeout_s
        elif (
            self._client_max_retries is not None
            and self._client_max_retries != max_retries
            or self._client_timeout_s is not None
            and self._client_timeout_s != timeout_s
        ):
            self._client = AsyncOpenAI(
                timeout=timeout_s,
                max_retries=max_retries,
            )
            self._client_max_retries = max_retries
            self._client_timeout_s = timeout_s
        return self._client

    async def resolve(
        self,
        *,
        location_text: str,
        allowed_region_names: List[str],
        timeout_s: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        result, _ = await self._resolve_internal(
            location_text=location_text,
            allowed_region_names=allowed_region_names,
            timeout_s=timeout_s,
            raise_on_timeout=True,
        )
        return result

    async def resolve_with_debug(
        self,
        *,
        location_text: str,
        allowed_region_names: List[str],
        timeout_s: Optional[float] = None,
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        return await self._resolve_internal(
            location_text=location_text,
            allowed_region_names=allowed_region_names,
            timeout_s=timeout_s,
            raise_on_timeout=False,
        )

    async def _resolve_internal(
        self,
        *,
        location_text: str,
        allowed_region_names: List[str],
        timeout_s: Optional[float] = None,
        raise_on_timeout: bool = True,
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Resolve a location string via LLM.

        Returns:
            {"neighborhoods": [...], "confidence": float, "reason": str} or None
        """
        normalized = " ".join(str(location_text or "").strip().split())
        debug_info: Dict[str, Any] = {
            "normalized": normalized,
            "candidates": list(allowed_region_names),
            "prompt": None,
            "raw_response": None,
            "model": None,
            "timeout_s": None,
        }
        if not normalized:
            debug_info["reason"] = "empty_query"
            return None, debug_info

        if not allowed_region_names:
            debug_info["reason"] = "no_candidates"
            return None, debug_info

        if not os.getenv("OPENAI_API_KEY"):
            debug_info["reason"] = "missing_api_key"
            return None, debug_info

        config = get_search_config()
        model = settings.openai_location_model
        debug_info["model"] = model

        timeout_ms = getattr(config, "location_timeout_ms", DEFAULT_LOCATION_TIMEOUT_MS)
        effective_timeout_s = timeout_s if timeout_s is not None else (timeout_ms / 1000.0)
        debug_info["timeout_s"] = effective_timeout_s

        client = self.client
        client_timeout_s = self._client_timeout_s
        if effective_timeout_s and client_timeout_s and effective_timeout_s > client_timeout_s:
            max_retries = self._coerce_max_retries(getattr(config, "max_retries", 2))
            client = AsyncOpenAI(timeout=effective_timeout_s, max_retries=max_retries)

        # Keep prompt size bounded: region_boundaries is ~300 rows for NYC, safe to include.
        neighborhoods_block = "\n".join(f"- {name}" for name in allowed_region_names)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(neighborhoods=neighborhoods_block)
        debug_info["prompt"] = system_prompt

        logger.debug(
            "[LOCATION LLM] Candidates (%s): %s",
            len(allowed_region_names),
            allowed_region_names,
        )
        logger.debug("[LOCATION LLM] Prompt: %s", system_prompt)

        try:
            request_kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Location query: {normalized}"},
                ],
                "response_format": {"type": "json_object"},
            }
            # GPT-5 models require `max_completion_tokens` (not `max_tokens`) and currently only
            # support default temperature.
            if not str(model).startswith("gpt-5"):
                request_kwargs["temperature"] = 0.1
                request_kwargs["max_tokens"] = 250
            else:
                request_kwargs["max_completion_tokens"] = 250

            async def _send_request() -> Any:
                if effective_timeout_s and effective_timeout_s > 0:
                    return await asyncio.wait_for(
                        client.chat.completions.create(**request_kwargs),
                        timeout=effective_timeout_s,
                    )
                return await client.chat.completions.create(**request_kwargs)

            async with OPENAI_CALL_SEMAPHORE:
                response = await _send_request()
            content = response.choices[0].message.content
            debug_info["raw_response"] = content
            logger.debug("[LOCATION LLM] Raw response: %s", content)
            if not content:
                debug_info["reason"] = "empty_response"
                return None, debug_info

            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                debug_info["reason"] = "invalid_json"
                return None, debug_info

            neighborhoods = parsed.get("neighborhoods")
            if not isinstance(neighborhoods, list):
                debug_info["reason"] = "invalid_neighborhoods"
                return None, debug_info

            confidence = parsed.get("confidence")
            try:
                confidence_val = float(confidence) if confidence is not None else 0.5
            except Exception:
                confidence_val = 0.5

            # De-dupe while preserving order; cap to 5.
            out_names: List[str] = []
            seen: set[str] = set()
            allowed_lower = {n.lower(): n for n in allowed_region_names}
            for item in neighborhoods:
                if not isinstance(item, str):
                    continue
                key = item.strip().lower()
                canonical = allowed_lower.get(key)
                if not canonical:
                    continue
                if canonical.lower() in seen:
                    continue
                seen.add(canonical.lower())
                out_names.append(canonical)
                if len(out_names) >= 5:
                    break

            if not out_names:
                debug_info["reason"] = "no_valid_candidates"
                return None, debug_info

            return (
                {
                    "neighborhoods": out_names,
                    "confidence": max(0.0, min(1.0, confidence_val)),
                    "reason": str(parsed.get("reason") or ""),
                },
                debug_info,
            )
        except asyncio.TimeoutError:
            logger.warning("Location LLM timed out for '%s'", normalized)
            debug_info["reason"] = "timeout"
            if raise_on_timeout:
                raise
            return None, debug_info
        except OpenAIError as exc:
            message = str(exc).lower()
            if "timed out" in message:
                logger.warning("Location LLM API timed out for '%s'", normalized)
                debug_info["reason"] = "timeout"
                if raise_on_timeout:
                    raise asyncio.TimeoutError() from exc
                return None, debug_info
            logger.debug("Location LLM resolution failed for '%s': %s", normalized, str(exc))
            debug_info["reason"] = "openai_error"
            debug_info["error"] = str(exc)
            return None, debug_info
        except Exception as exc:
            logger.debug("Location LLM resolution failed for '%s': %s", normalized, str(exc))
            debug_info["reason"] = "exception"
            debug_info["error"] = str(exc)
            return None, debug_info
