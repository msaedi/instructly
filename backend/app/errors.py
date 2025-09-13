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
    return problem


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[override]
        problem = _problem(
            status=exc.status_code,
            detail=str(exc.detail) if exc.detail else None,
            instance=request.url.path,
        )
        return JSONResponse(
            problem, status_code=exc.status_code, media_type="application/problem+json"
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):  # type: ignore[override]
        problem = _problem(
            status=exc.status_code,
            detail=str(exc.detail) if exc.detail else None,
            instance=request.url.path,
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
        )
        # Include errors for debugging/clients
        problem["errors"] = exc.errors()
        return JSONResponse(problem, status_code=422, media_type="application/problem+json")

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError):  # type: ignore[override]
        problem = _problem(
            status=422,
            type_="https://example.com/problems/validation",
            title=_title_from_status(422),
            detail="Validation failed",
            instance=request.url.path,
        )
        problem["errors"] = exc.errors()
        return JSONResponse(problem, status_code=422, media_type="application/problem+json")

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):  # type: ignore[override]
        problem = _problem(
            status=500,
            detail="An unexpected error occurred",
            instance=request.url.path,
        )
        return JSONResponse(problem, status_code=500, media_type="application/problem+json")
