import logging

from ..core.constants import SSE_PATH_PREFIX
from ..database import SessionLocal
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

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
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
                db.close()
        except Exception as e:
            # Never break the response due to header resolution failures
            logger.debug(f"BetaPhaseHeaderMiddleware error: {e}")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers.append((b"x-beta-phase", phase_value))
                headers.append((b"x-beta-allow-signup", allow_signup_value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
