from typing import Any, Awaitable, Callable, Dict

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Any]]
Send = Callable[[Dict[str, Any]], Awaitable[Any]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class GZipMiddleware:
    app: ASGIApp

    def __init__(self, app: ASGIApp, minimum_size: int = ...) -> None: ...

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...
