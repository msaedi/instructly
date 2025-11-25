from fastapi.testclient import TestClient


def _make_client(monkeypatch, overrides):
    monkeypatch.delenv('STRICT_SCHEMAS', raising=False)
    from importlib import reload

    import app.api.dependencies as api_dependencies  # noqa: F401
    import app.main as main

    reload(main)
    client = TestClient(main.fastapi_app, raise_server_exceptions=False)
    for dep, override in overrides.items():
        main.fastapi_app.dependency_overrides[dep] = override

    for route in main.fastapi_app.routes:
        if getattr(route, 'path', '').startswith('/auth') or getattr(route, 'path', '').startswith('/bookings') or getattr(route, 'path', '').startswith('/api/payments'):
            for dep in getattr(route, 'dependencies', []) or []:
                main.fastapi_app.dependency_overrides.setdefault(dep.dependency, lambda: None)

    return client, main


def _problem_keys(body):
    return {k: body.get(k) for k in ['type', 'title', 'detail', 'status', 'instance', 'code']}


def test_auth_login_problem_contract(monkeypatch):
    import app.api.dependencies.services as service_deps

    class DummyAuthService:
        def authenticate_user(self, *_, **__):
            return None

    client, main = _make_client(monkeypatch, {service_deps.get_auth_service: lambda: DummyAuthService()})
    try:
        resp = client.post('/auth/login', data={'username': 'foo@example.com', 'password': 'bad'})
        assert resp.status_code == 401
        body = resp.json()
        assert _problem_keys(body) == {
            'type': 'about:blank',
            'title': 'Unauthorized',
            'detail': 'Incorrect email or password',
            'status': 401,
            'instance': '/auth/login',
            'code': 'AUTH_INVALID_CREDENTIALS',
        }
    finally:
        main.fastapi_app.dependency_overrides.clear()


def test_bookings_problem_contract(monkeypatch):
    from types import SimpleNamespace

    import app.api.dependencies as api_dependencies

    dummy_user = SimpleNamespace(id='user_123', roles=[], is_instructor=False)

    class DummyBookingService:
        async def create_booking_with_payment_setup(self, *_, **__):  # pragma: no cover
            raise AssertionError('service should not execute')

    client, main = _make_client(
        monkeypatch,
        {
            api_dependencies.get_current_active_user: lambda: dummy_user,
            api_dependencies.get_booking_service: lambda: DummyBookingService(),
        },
    )
    try:
        # Use v1 API path - legacy /bookings/ removed in Phase 9
        resp = client.post('/api/v1/bookings', json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body.get('code') == 'validation_error'
        assert body.get('status') == 422
        assert body.get('title') == 'Unprocessable Entity'
        assert body.get('instance') == '/api/v1/bookings'
        assert 'errors' in body
    finally:
        main.fastapi_app.dependency_overrides.clear()


def test_payments_instructor_guard_problem_contract(monkeypatch):
    from types import SimpleNamespace

    import app.api.dependencies.auth as auth_deps
    import app.routes.payments as payments_routes  # noqa: F401

    dummy_user = SimpleNamespace(id='user_123', roles=[], is_instructor=False, is_student=True)

    class DummyStripeService:
        pass

    overrides = {
        auth_deps.get_current_active_user: lambda: dummy_user,
    }

    from app.routes.payments import get_stripe_service  # type: ignore  # noqa: E402

    overrides[get_stripe_service] = lambda: DummyStripeService()

    client, main = _make_client(monkeypatch, overrides)
    try:
        resp = client.post('/api/payments/connect/onboard')
        assert resp.status_code == 403
        body = resp.json()
        assert _problem_keys(body) == {
            'type': 'about:blank',
            'title': 'Forbidden',
            'detail': 'This endpoint requires instructor role',
            'status': 403,
            'instance': '/api/payments/connect/onboard',
            'code': 'PAYMENTS_INSTRUCTOR_ONLY',
        }
    finally:
        main.fastapi_app.dependency_overrides.clear()
