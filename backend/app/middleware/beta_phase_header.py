import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..core.constants import SSE_PATH_PREFIX
from ..database import SessionLocal
from ..monitoring.prometheus_metrics import PrometheusMetrics
from ..repositories.beta_repository import BetaSettingsRepository

logger = logging.getLogger(__name__)


class BetaPhaseHeaderMiddleware:
    """
    ASGI middleware that attaches the current beta phase to every HTTP response header.

    - Reads settings via repository pattern
    - Skips SSE endpoints
    - Sets header: x-beta-phase: disabled | instructor_only | open_beta
    - Sets header: x-beta-allow-signup: 1 | 0 (true when signup allowed without invite)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip Server-Sent Events endpoints
        path = scope.get("path", "")
        if path.startswith(SSE_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        # Resolve beta phase once per request
        phase_value = b"unknown"
        allow_signup_value = b"0"
        try:
            db = SessionLocal()
            try:
                repo = BetaSettingsRepository(db)
                s = repo.get_singleton()
                if bool(s.beta_disabled):
                    phase_value = b"disabled"
                else:
                    # Ensure plain string
                    phase_value = str(s.beta_phase).encode("utf-8")
                allow_signup_value = b"1" if bool(s.allow_signup_without_invite) else b"0"
            finally:
                # async-blocking-ignore: Middleware cleanup <1ms
                db.rollback()  # Clean up transaction before returning to pool  # async-blocking-ignore
                db.close()
        except Exception as e:
            # Never break the response due to header resolution failures
            logger.debug(f"BetaPhaseHeaderMiddleware error: {e}")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-beta-phase", phase_value))
                headers.append((b"x-beta-allow-signup", allow_signup_value))
                message = {**message, "headers": headers}
                # Record header distribution
                try:
                    PrometheusMetrics.inc_beta_phase_header(phase_value.decode("utf-8"))
                except Exception:
                    pass
            await send(message)

        await self.app(scope, receive, send_wrapper)
