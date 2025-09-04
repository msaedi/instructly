from typing import Optional

from fastapi import Request


def resolve_identity(req: Request) -> str:
    """
    Precedence:
    1) authenticated user id if available on request.state.user.id or request.state.user_id
    2) client IP
    """
    try:
        user = getattr(req.state, "user", None)
        user_id: Optional[str] = getattr(user, "id", None) if user is not None else None
        if not user_id:
            user_id = getattr(req.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"
    except Exception:
        pass

    client = getattr(req, "client", None)
    ip = getattr(client, "host", None) if client else None
    if not ip:
        ip = req.headers.get("x-forwarded-for", "unknown")
    return f"ip:{ip}"


def is_login_flow(req: Request) -> bool:
    # Placeholder for future PR: tag subsequent requests for ~10s after POST /auth/login
    return bool(getattr(req.state, "login_flow", False))
