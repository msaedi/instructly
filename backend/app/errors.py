from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


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


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[override]
        detail_text, code, errors = _parse_detail(exc.detail)
        problem = _problem(
            status=exc.status_code,
            detail=detail_text,
            instance=request.url.path,
            code=code,
            errors=errors,
        )
        return JSONResponse(
            problem, status_code=exc.status_code, media_type="application/problem+json"
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):  # type: ignore[override]
        detail_text, code, errors = _parse_detail(exc.detail)
        problem = _problem(
            status=exc.status_code,
            detail=detail_text,
            instance=request.url.path,
            code=code,
            errors=errors,
        )
        return JSONResponse(
            problem, status_code=exc.status_code, media_type="application/problem+json"
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError):  # type: ignore[override]
        problem = _problem(
            status=422,
            type_="https://example.com/problems/validation",
            title=_title_from_status(422),
            detail="Request validation failed",
            instance=request.url.path,
            code="validation_error",
            errors=exc.errors(),
        )
        return JSONResponse(problem, status_code=422, media_type="application/problem+json")

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError):  # type: ignore[override]
        problem = _problem(
            status=422,
            type_="https://example.com/problems/validation",
            title=_title_from_status(422),
            detail="Validation failed",
            instance=request.url.path,
            code="validation_error",
            errors=exc.errors(),
        )
        return JSONResponse(problem, status_code=422, media_type="application/problem+json")

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):  # type: ignore[override]
        problem = _problem(
            status=500,
            detail="An unexpected error occurred",
            instance=request.url.path,
            code="internal_server_error",
        )
        return JSONResponse(problem, status_code=500, media_type="application/problem+json")
