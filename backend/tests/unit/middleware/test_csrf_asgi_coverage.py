from types import SimpleNamespace

import pytest

from app.middleware.csrf_asgi import CsrfOriginMiddlewareASGI


async def _run_app(app, scope):
    messages = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return messages


def _scope(method="POST", path="/api/v1/test", headers=None):
    headers = headers or {}
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }


@pytest.mark.asyncio
async def test_csrf_allows_non_http():
    called = {"hit": False}

    async def app(scope, receive, send):
        called["hit"] = True

    middleware = CsrfOriginMiddlewareASGI(app)
    await middleware({"type": "lifespan"}, None, None)
    assert called["hit"] is True


@pytest.mark.asyncio
async def test_csrf_allows_get(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(is_testing=False, preview_frontend_domain="preview.example.com"),
    )
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(middleware, _scope(method="GET"))
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_csrf_disabled_for_tests(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(is_testing=True, preview_frontend_domain="preview.example.com"),
    )
    monkeypatch.setenv("DISABLE_CSRF_FOR_TESTS", "true")
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(middleware, _scope())
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_csrf_allows_webhook_path(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(is_testing=False, preview_frontend_domain="preview.example.com"),
    )
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(middleware, _scope(path="/api/v1/payments/webhooks/stripe"))
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_csrf_blocks_invalid_origin(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(
            is_testing=False,
            preview_frontend_domain="preview.example.com",
            prod_frontend_origins_csv="https://app.instainstru.com",
        ),
    )
    monkeypatch.setenv("SITE_MODE", "prod")
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(
        middleware, _scope(headers={"origin": "https://evil.example.com"})
    )
    assert messages[0]["status"] == 403


@pytest.mark.asyncio
async def test_csrf_allows_matching_origin(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(
            is_testing=False,
            preview_frontend_domain="preview.example.com",
            prod_frontend_origins_csv="https://app.instainstru.com",
        ),
    )
    monkeypatch.setenv("SITE_MODE", "production")
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(
        middleware, _scope(headers={"origin": "https://app.instainstru.com"})
    )
    assert messages[0]["status"] == 200


def test_allowed_frontend_host_preview(monkeypatch):
    middleware = CsrfOriginMiddlewareASGI(lambda *_args: None)
    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(preview_frontend_domain="preview.example.com"),
    )
    monkeypatch.setenv("SITE_MODE", "preview")
    assert middleware._allowed_frontend_host() == "preview.example.com"


def test_allowed_frontend_host_prod_defaults(monkeypatch):
    middleware = CsrfOriginMiddlewareASGI(lambda *_args: None)
    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(preview_frontend_domain="preview.example.com", prod_frontend_origins_csv=""),
    )
    monkeypatch.setenv("SITE_MODE", "production")
    assert middleware._allowed_frontend_host() == "app.instainstru.com"


def test_allowed_frontend_host_handles_bad_url(monkeypatch):
    middleware = CsrfOriginMiddlewareASGI(lambda *_args: None)
    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(
            preview_frontend_domain="preview.example.com",
            prod_frontend_origins_csv="https://bad[.example.com",
        ),
    )
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr("app.middleware.csrf_asgi.urlparse", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad")))
    assert middleware._allowed_frontend_host() == "https://bad[.example.com"


def test_csrf_disabled_for_tests_handles_settings_error(monkeypatch):
    class _BrokenSettings:
        @property
        def is_testing(self):
            raise RuntimeError("boom")

    middleware = CsrfOriginMiddlewareASGI(lambda *_args: None)
    monkeypatch.setattr("app.middleware.csrf_asgi.settings", _BrokenSettings())
    assert middleware._csrf_disabled_for_tests() is False


@pytest.mark.asyncio
async def test_csrf_exempts_auth_path_in_tests(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(
            is_testing=True,
            preview_frontend_domain="preview.example.com",
            prod_frontend_origins_csv="https://app.instainstru.com",
        ),
    )
    monkeypatch.setenv("SITE_MODE", "prod")
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(
        middleware, _scope(path="/api/v1/auth/login", headers={"origin": "https://evil.com"})
    )
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_csrf_allows_matching_referer(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(
            is_testing=False,
            preview_frontend_domain="preview.example.com",
            prod_frontend_origins_csv="https://app.instainstru.com",
        ),
    )
    monkeypatch.setenv("SITE_MODE", "prod")
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(
        middleware, _scope(headers={"referer": "https://app.instainstru.com/page"})
    )
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_csrf_allows_dev_mode(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(is_testing=False, preview_frontend_domain="preview.example.com"),
    )
    monkeypatch.setenv("SITE_MODE", "dev")
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(middleware, _scope(headers={"origin": "https://evil.com"}))
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_csrf_blocks_on_bad_header_decode(monkeypatch):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(
        "app.middleware.csrf_asgi.settings",
        SimpleNamespace(
            is_testing=False,
            preview_frontend_domain="preview.example.com",
            prod_frontend_origins_csv="https://app.instainstru.com",
        ),
    )
    monkeypatch.setenv("SITE_MODE", "prod")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [(b"\xff", b"\xff")],
    }
    middleware = CsrfOriginMiddlewareASGI(app)
    messages = await _run_app(middleware, scope)
    assert messages[0]["status"] == 403
