from typing import Any, Awaitable, Callable

from starlette.types import ASGIApp, Receive, Scope, Send


class BaseHTTPMiddleware:
    app: ASGIApp

    def __init__(self, app: ASGIApp) -> None: ...

    async def dispatch(self, request: Any, call_next: Callable[[Any], Awaitable[Any]]) -> Any: ...

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...
