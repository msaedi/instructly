from types import SimpleNamespace

from starlette.requests import Request

from app.ratelimit import identity as rl_identity


def _make_request(headers=None):
    headers = headers or {}
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def test_resolve_identity_uses_user_id():
    req = _make_request()
    req.state.user = SimpleNamespace(id="user-123")
    assert rl_identity.resolve_identity(req) == "user:user-123"


def test_resolve_identity_uses_state_user_id():
    req = _make_request()
    req.state.user_id = "user-456"
    assert rl_identity.resolve_identity(req) == "user:user-456"


def test_resolve_identity_falls_back_to_ip():
    req = _make_request(headers={"x-forwarded-for": "1.2.3.4"})
    assert rl_identity.resolve_identity(req) == "ip:1.2.3.4"


def test_is_login_flow_flag():
    req = _make_request()
    req.state.login_flow = True
    assert rl_identity.is_login_flow(req) is True
