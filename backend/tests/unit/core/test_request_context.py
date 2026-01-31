from __future__ import annotations

import asyncio
import io
import logging

import pytest

from app.core.request_context import (
    RequestIdFilter,
    get_request_id,
    get_request_id_value,
    reset_request_id,
    set_request_id,
    with_request_id_header,
)


def test_set_get_reset_request_id() -> None:
    token = set_request_id("req-123")
    assert get_request_id() == "req-123"
    reset_request_id(token)
    assert get_request_id() is None


def test_get_request_id_default() -> None:
    assert get_request_id("fallback") == "fallback"
    assert get_request_id_value() == "no-request"


@pytest.mark.asyncio
async def test_request_id_isolated_between_tasks() -> None:
    async def _capture(value: str) -> str | None:
        token = set_request_id(value)
        await asyncio.sleep(0)
        result = get_request_id()
        reset_request_id(token)
        return result

    first, second = await asyncio.gather(_capture("req-a"), _capture("req-b"))
    assert {first, second} == {"req-a", "req-b"}


def test_with_request_id_header() -> None:
    assert with_request_id_header() is None
    token = set_request_id("req-xyz")
    try:
        assert with_request_id_header() == {"request_id": "req-xyz"}
        assert with_request_id_header({"x": "1"}) == {"x": "1", "request_id": "req-xyz"}
    finally:
        reset_request_id(token)


def test_logging_filter_injects_request_id() -> None:
    logger = logging.getLogger("request-context-test")
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(request_id)s %(message)s"))
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)
    logger.propagate = False

    try:
        token = set_request_id("req-555")
        logger.info("inside")
        reset_request_id(token)
        logger.info("outside")
    finally:
        logger.removeHandler(handler)

    lines = stream.getvalue().strip().splitlines()
    assert lines[0].startswith("req-555 ")
    assert lines[1].startswith("no-request ")
