"""Strict API Router requiring response_model on all routes.

This utility provides a router that enforces OpenAPI response schema requirements
at import time rather than relying on pre-commit or CI checks.

Usage:
    from app.utils.strict_router import StrictAPIRouter

    router = StrictAPIRouter(tags=["my-routes"])

    # This works - has response_model
    @router.get("/items", response_model=ItemListResponse)
    async def list_items(): ...

    # This works - 204 No Content
    @router.delete("/items/{id}", status_code=204)
    async def delete_item(): ...

    # This FAILS at import time - no response_model or 204
    @router.get("/items/{id}")
    async def get_item(): ...  # ValueError raised!
"""

from __future__ import annotations

from typing import Any, Callable, Type

from fastapi import APIRouter
from pydantic import BaseModel

# Sentinel value to detect missing response_model
_MISSING = object()


class StrictAPIRouter(APIRouter):
    """APIRouter that enforces response_model or status_code=204.

    This router raises ValueError at route registration time if an endpoint
    doesn't have either:
    - A response_model parameter (not None)
    - A status_code of 204 (No Content)

    This catches missing response schemas at import time rather than in CI.
    """

    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        response_model: Type[BaseModel] | None = _MISSING,  # type: ignore[assignment]
        status_code: int = 200,
        **kwargs: Any,
    ) -> None:
        """Add a route with strict response model requirements.

        Args:
            path: The URL path for this route
            endpoint: The endpoint function
            response_model: Pydantic model for the response (required unless 204)
            status_code: HTTP status code (use 204 for no-content responses)
            **kwargs: Additional arguments passed to APIRouter.add_api_route

        Raises:
            ValueError: If response_model is missing and status_code is not 204
        """
        # Check if response_model was explicitly provided
        if response_model is _MISSING and status_code != 204:
            raise ValueError(
                f"StrictAPIRouter requires response_model for '{path}' "
                f"({endpoint.__name__}). Either add response_model=YourModel "
                f"or use status_code=204 for no-content responses."
            )

        # Convert _MISSING to None for the parent call
        actual_response_model = None if response_model is _MISSING else response_model

        super().add_api_route(
            path,
            endpoint,
            response_model=actual_response_model,
            status_code=status_code,
            **kwargs,
        )
