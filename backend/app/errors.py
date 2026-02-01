import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _title_from_status(status_code: int) -> str:
    mapping = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }
    return mapping.get(status_code, "Error")


def _problem(
    *,
    status: int,
    title: Optional[str] = None,
    detail: Optional[str] = None,
    instance: Optional[str] = None,
    type_: str = "about:blank",
    code: Optional[str] = None,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    errors: Optional[Any] = None,
) -> Dict[str, Any]:
    problem: Dict[str, Any] = {
        "type": type_,
        "title": title or _title_from_status(status),
        "status": status,
        "detail": detail or "",
        "instance": instance or "",
    }
    if code:
        problem["code"] = code
    if request_id:
        problem["request_id"] = request_id
    if trace_id:
        problem["trace_id"] = trace_id
    if errors is not None:
        problem["errors"] = errors
    return problem


def _parse_detail(detail: Any) -> tuple[Optional[str], Optional[str], Optional[Any]]:
    if isinstance(detail, dict):
        code = detail.get("code") if isinstance(detail.get("code"), str) else None
        message = detail.get("message") or detail.get("detail")
        detail_text = message if isinstance(message, str) else None
        errors = detail.get("details") or detail.get("errors")
        return detail_text, code, errors
    if isinstance(detail, str):
        return detail, None, None
    if detail is None:
        return None, None, None
    return str(detail), None, None


def _extract_request_id(request: Request) -> Optional[str]:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return str(request_id)
    header_id = request.headers.get("x-request-id")
    return str(header_id) if header_id else None


def _extract_trace_id() -> Optional[str]:
    try:
        # Lazy import to avoid circular dependencies and ensure OTel
        # modules are only loaded when actually needed.
        from app.monitoring.otel import get_current_trace_id, is_otel_enabled
    except Exception:
        logger.debug("Failed to extract OTel trace ID", exc_info=True)
        return None
    if not is_otel_enabled():
        return None
    return get_current_trace_id()


def _extract_detail_extras(detail: Any) -> tuple[Optional[str], Dict[str, Any]]:
    override_title: Optional[str] = None
    extras: Dict[str, Any] = {}
    if not isinstance(detail, dict):
        return override_title, extras

    maybe_title = detail.get("title")
    if isinstance(maybe_title, str) and maybe_title.strip():
        override_title = maybe_title
    error_value = detail.get("error")
    if isinstance(error_value, str):
        extras["error"] = error_value
    current_version = detail.get("current_version")
    if isinstance(current_version, str):
        extras["current_version"] = current_version
    checkr_error = detail.get("checkr_error")
    if checkr_error is not None:
        extras["checkr_error"] = jsonable_encoder(checkr_error)
    provider_error = detail.get("provider_error")
    if provider_error is not None:
        extras["provider_error"] = jsonable_encoder(provider_error)
    debug_info = detail.get("debug")
    if debug_info is not None:
        extras["debug"] = jsonable_encoder(debug_info)

    return override_title, extras


def _with_request_id_header(
    headers: Optional[Dict[str, str]],
    request_id: Optional[str],
) -> Optional[Dict[str, str]]:
    if not request_id:
        return headers
    merged = dict(headers or {})
    merged.setdefault("X-Request-ID", request_id)
    return merged


def register_error_handlers(app: FastAPI) -> None:
    strict_schemas = os.getenv("STRICT_SCHEMAS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    default_media_type = "application/problem+json" if strict_schemas else "application/json"

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = _extract_request_id(request)
        trace_id = _extract_trace_id()
        detail_text, code, errors = _parse_detail(exc.detail)
        override_title, extras = _extract_detail_extras(exc.detail)
        problem = _problem(
            status=exc.status_code,
            title=override_title,
            detail=detail_text,
            instance=request.url.path,
            code=code,
            request_id=request_id,
            trace_id=trace_id,
            errors=jsonable_encoder(errors) if errors is not None else None,
        )
        if extras:
            problem.update(extras)
        return JSONResponse(
            problem,
            status_code=exc.status_code,
            media_type=default_media_type,
            headers=_with_request_id_header(exc.headers, request_id),
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = _extract_request_id(request)
        trace_id = _extract_trace_id()
        detail_text, code, errors = _parse_detail(exc.detail)
        override_title, extras = _extract_detail_extras(exc.detail)
        problem = _problem(
            status=exc.status_code,
            title=override_title,
            detail=detail_text,
            instance=request.url.path,
            code=code,
            request_id=request_id,
            trace_id=trace_id,
            errors=jsonable_encoder(errors) if errors is not None else None,
        )
        if extras:
            problem.update(extras)
        return JSONResponse(
            problem,
            status_code=exc.status_code,
            media_type=default_media_type,
            headers=_with_request_id_header(exc.headers, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _extract_request_id(request)
        trace_id = _extract_trace_id()
        if strict_schemas:
            problem = _problem(
                status=422,
                type_="https://example.com/problems/validation",
                title=_title_from_status(422),
                detail="Request validation failed",
                instance=request.url.path,
                code="validation_error",
                request_id=request_id,
                trace_id=trace_id,
                errors=jsonable_encoder(exc.errors()),
            )
            return JSONResponse(
                problem,
                status_code=422,
                media_type=default_media_type,
                headers=_with_request_id_header(None, request_id),
            )
        detail_list = jsonable_encoder(exc.errors())
        return JSONResponse(
            content={
                "type": "about:blank",
                "title": _title_from_status(422),
                "status": 422,
                "detail": detail_list,
                "instance": request.url.path,
                "code": "validation_error",
                "request_id": request_id,
                "trace_id": trace_id,
                "errors": detail_list,
            },
            status_code=422,
            media_type="application/json",
            headers=_with_request_id_header(None, request_id),
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
        request_id = _extract_request_id(request)
        trace_id = _extract_trace_id()
        if strict_schemas:
            problem = _problem(
                status=422,
                type_="https://example.com/problems/validation",
                title=_title_from_status(422),
                detail="Validation failed",
                instance=request.url.path,
                code="validation_error",
                request_id=request_id,
                trace_id=trace_id,
                errors=jsonable_encoder(exc.errors()),
            )
            return JSONResponse(
                problem,
                status_code=422,
                media_type=default_media_type,
                headers=_with_request_id_header(None, request_id),
            )
        detail_list = jsonable_encoder(exc.errors())
        return JSONResponse(
            content={
                "type": "about:blank",
                "title": _title_from_status(422),
                "status": 422,
                "detail": detail_list,
                "instance": request.url.path,
                "code": "validation_error",
                "request_id": request_id,
                "trace_id": trace_id,
                "errors": detail_list,
            },
            status_code=422,
            media_type="application/json",
            headers=_with_request_id_header(None, request_id),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _extract_request_id(request)
        trace_id = _extract_trace_id()
        problem = _problem(
            status=500,
            detail="Internal Server Error",
            instance=request.url.path,
            code="internal_server_error",
            request_id=request_id,
            trace_id=trace_id,
        )
        return JSONResponse(
            problem,
            status_code=500,
            media_type=default_media_type,
            headers=_with_request_id_header(None, request_id),
        )
