from __future__ import annotations

from contextvars import ContextVar, Token
import logging
from typing import Optional

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(request_id: Optional[str]) -> Token[str]:
    return _request_id_var.set(request_id or "")


def reset_request_id(token: Token[str]) -> None:
    _request_id_var.reset(token)


def get_request_id(default: Optional[str] = None) -> Optional[str]:
    value = _request_id_var.get()
    return value if value else default


def get_request_id_value(default: str = "no-request") -> str:
    value = _request_id_var.get()
    return value if value else default


def with_request_id_header(
    headers: Optional[dict[str, str]] = None,
) -> Optional[dict[str, str]]:
    request_id = get_request_id()
    if not request_id:
        return headers
    merged = dict(headers or {})
    merged.setdefault("request_id", request_id)
    return merged


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id_value()
        if not hasattr(record, "otelTraceID"):
            record.otelTraceID = "no-trace"
        if not hasattr(record, "otelSpanID"):
            record.otelSpanID = "no-span"
        return True


def attach_request_id_filter(logger: Optional[logging.Logger] = None) -> None:
    target = logger or logging.getLogger()
    for handler in target.handlers:
        handler.addFilter(RequestIdFilter())
