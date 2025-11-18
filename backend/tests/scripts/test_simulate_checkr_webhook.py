from importlib import import_module
from pathlib import Path
import sys
import types

import pytest

from app.routes.webhooks_checkr import _compute_signature

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sim = import_module("scripts.simulate_checkr_webhook")


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in [
        "DATABASE_URL",
        "SITE_MODE",
        "CHECKR_WEBHOOK_URL",
        "SIM_ENV_FILE",
        "SIM_ENV_NAME",
    ]:
        monkeypatch.delenv(key, raising=False)


def _write_env(tmp_path, content: str) -> str:
    path = tmp_path / ".env"
    path.write_text(content)
    return str(path)


def _make_dummy_session(report_id: str = "report"):
    class Session:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, exc_type, exc, tb):
            return False

        def query(self_inner, model):
            class Query:
                def __init__(self, model):
                    self.model = model

                def filter(self, *args, **kwargs):
                    return self

                def one_or_none(self):
                    if self.model.__name__ == "User":
                        return types.SimpleNamespace(id="user", email="johnsmith@example.com")
                    return types.SimpleNamespace(
                        id="profile",
                        bgc_status="pending",
                        bgc_report_id=report_id,
                    )

                def one(self):
                    return types.SimpleNamespace(
                        id="profile",
                        bgc_status="passed",
                        bgc_report_id=report_id,
                    )

            return Query(model)

        def add(self_inner, *_):
            pass

        def commit(self_inner):
            pass

        def refresh(self_inner, *_):
            pass

        def expire_all(self_inner):
            pass

        def close(self_inner):
            pass

    return Session()


def test_bootstrap_env_beta_prefers_prod_service(tmp_path, monkeypatch):
    env_path = _write_env(
        tmp_path,
        "\n".join(
            [
                "prod_database_url=postgresql://prod-user@host/prod",
                "prod_service_database_url=postgresql://service-user@host/prod",
                "CHECKR_WEBHOOK_SECRET=supersecret",
            ]
        ),
    )

    env_name = sim._bootstrap_env("beta", env_path)

    assert env_name == "beta"
    assert (
        sim.os.environ["DATABASE_URL"]
        == "postgresql://service-user@host/prod"
    )
    assert sim.os.environ["SITE_MODE"] == "prod"
    assert "CHECKR_WEBHOOK_URL" not in sim.os.environ
    assert sim.os.environ["CHECKR_WEBHOOK_SECRET"] == "supersecret"


def test_bootstrap_env_stg_defaults_localhost_webhook(tmp_path):
    env_path = _write_env(
        tmp_path,
        "stg_database_url=postgresql://stg-user@host/stg\n",
    )

    env_name = sim._bootstrap_env("stg", env_path)

    assert env_name == "stg"
    assert sim.os.environ["SITE_MODE"] == "stg"
    assert sim.os.environ["CHECKR_WEBHOOK_URL"] == "http://localhost:8000/webhooks/checkr/"


@pytest.mark.parametrize(
    "environment,expected",
    [
        ("beta", "https://api.instainstru.com/webhooks/checkr/"),
        ("prod", "https://api.instainstru.com/webhooks/checkr/"),
        ("preview", "https://preview-api.instainstru.com/webhooks/checkr/"),
        ("stg", "http://localhost:8000/webhooks/checkr/"),
        ("int", "http://localhost:8000/webhooks/checkr/"),
    ],
)
def test_resolve_webhook_url_defaults(environment, expected):
    settings_stub = types.SimpleNamespace()
    result = sim._resolve_webhook_url(
        explicit=None,
        current_settings=settings_stub,
        environment=environment,
    )
    assert result == expected


def test_signature_matches_server_helper(monkeypatch):
    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_1", "status": "completed", "result": "clear"}},
    }
    raw_body = sim.json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    secret = "secret-value"

    monkeypatch.setenv("CHECKR_WEBHOOK_SECRET", secret)

    signature = sim.hmac.new(secret.encode("utf-8"), raw_body, sim.hashlib.sha256).hexdigest()
    assert signature == _compute_signature(secret, raw_body)


def test_requests_post_uses_raw_body(monkeypatch, tmp_path):
    captured = {}

    env_path = _write_env(
        tmp_path,
        "\n".join(
            [
                "prod_database_url=postgresql://prod-user@host/prod",
                "prod_service_database_url=postgresql://service-user@host/prod",
                "CHECKR_WEBHOOK_SECRET=secret-val",
            ]
        ),
    )

    monkeypatch.setattr("app.database.SessionLocal", lambda: _make_dummy_session("report-1"))
    monkeypatch.setattr(
        "app.repositories.instructor_profile_repository.InstructorProfileRepository",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "app.services.background_check_service.BackgroundCheckService",
        lambda *_, **__: types.SimpleNamespace(
            invite=lambda *_: types.SimpleNamespace(__await__=lambda self: iter(["report-1"])),
            update_status_from_report=lambda *a, **k: None,
        ),
    )
    monkeypatch.setattr(sim.asyncio, "run", lambda coro: "report-1")

    def dummy_session():
        class Session:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

            def query(self_inner, model):
                class Query:
                    def filter(self, *args, **kwargs):
                        return self

                    def one_or_none(self):
                        if model.__name__ == "User":
                            return types.SimpleNamespace(id="user", email="johnsmith@example.com")
                        return types.SimpleNamespace(
                            id="profile",
                            bgc_status="pending",
                            bgc_report_id="report-1",
                        )

                    def one(self):
                        return types.SimpleNamespace(
                            id="profile",
                            bgc_status="passed",
                            bgc_report_id="report-1",
                        )

                return Query()

            def add(self_inner, *_):
                pass

            def commit(self_inner):
                pass

            def refresh(self_inner, *_):
                pass

            def expire_all(self_inner):
                pass

            def close(self_inner):
                pass

        return Session()

    monkeypatch.setattr("app.database.SessionLocal", dummy_session)

    class DummyRepo:
        def __init__(self, *_):
            pass

    monkeypatch.setattr(
        "app.repositories.instructor_profile_repository.InstructorProfileRepository",
        DummyRepo,
    )

    monkeypatch.setattr(
        "app.services.background_check_service.BackgroundCheckService",
        lambda *_, **__: types.SimpleNamespace(
            invite=lambda *_: types.SimpleNamespace(__await__=lambda self: iter(["report-1"])),
            update_status_from_report=lambda *a, **k: None,
        ),
    )

    monkeypatch.setattr(sim.asyncio, "run", lambda coro: "report-1")

    def fake_dispatch(url, body, signature):
        captured["url"] = url
        captured["body"] = body
        captured["signature"] = signature
        return 200, "{}"

    monkeypatch.setattr(sim, "_dispatch_webhook", fake_dispatch)
    monkeypatch.setattr(sim, "_post_webhook_via_asgi", lambda *a, **k: (200, "{}"))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "simulate_checkr_webhook.py",
            "--env",
            "beta",
            "--env-file",
            str(env_path),
            "--email",
            "johnsmith@example.com",
            "--result",
            "clear",
            "--force-prod",
            "--yes",
        ],
    )

    sim.main()

    expected_sig = _compute_signature("secret-val", captured["body"])
    assert captured["body"].startswith(b"{\"type\":\"report.completed\"")
    assert captured["signature"] == expected_sig


def test_api_key_preferred_over_webhook_secret(monkeypatch, tmp_path):
    env_path = _write_env(
        tmp_path,
        "\n".join(
            [
                "prod_database_url=postgresql://prod-user@host/prod",
                "prod_service_database_url=postgresql://service-user@host/prod",
                "CHECKR_WEBHOOK_SECRET=secret-val",
                "CHECKR_API_KEY=api-key-env",
            ]
        ),
    )

    monkeypatch.setattr("app.database.SessionLocal", lambda: _make_dummy_session("report-api"))
    monkeypatch.setattr(
        "app.repositories.instructor_profile_repository.InstructorProfileRepository",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "app.services.background_check_service.BackgroundCheckService",
        lambda *_, **__: types.SimpleNamespace(
            invite=lambda *_: types.SimpleNamespace(__await__=lambda self: iter(["report-api"])),
            update_status_from_report=lambda *a, **k: None,
        ),
    )
    monkeypatch.setattr(sim.asyncio, "run", lambda _: "report-api")

    sent: dict[str, bytes | str] = {}

    def fake_dispatch(url, body, signature):
        sent["body"] = body
        sent["signature"] = signature
        return 200, "{}"

    monkeypatch.setattr(sim, "_dispatch_webhook", fake_dispatch)
    monkeypatch.setattr(sim, "_post_webhook_via_asgi", lambda *a, **k: (200, "{}"))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "simulate_checkr_webhook.py",
            "--env",
            "beta",
            "--env-file",
            str(env_path),
            "--email",
            "johnsmith@example.com",
            "--result",
            "clear",
            "--force-prod",
            "--yes",
        ],
    )

    sim.main()

    expected_sig = _compute_signature("api-key-env", sent["body"])
    assert sent["signature"] == expected_sig


def test_sig_format_sha256(monkeypatch, tmp_path):
    env_path = _write_env(
        tmp_path,
        "\n".join(
            [
                "prod_database_url=postgresql://prod-user@host/prod",
                "prod_service_database_url=postgresql://service-user@host/prod",
                "CHECKR_WEBHOOK_SECRET=secret-val",
            ]
        ),
    )

    sent = {}

    def fake_dispatch(url, body, signature):
        sent["signature"] = signature
        return 200, "{}"

    monkeypatch.setattr("app.database.SessionLocal", lambda: _make_dummy_session("report"))
    monkeypatch.setattr(
        "app.repositories.instructor_profile_repository.InstructorProfileRepository",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "app.services.background_check_service.BackgroundCheckService",
        lambda *_, **__: types.SimpleNamespace(
            invite=lambda *_: types.SimpleNamespace(__await__=lambda self: iter(["report"])),
            update_status_from_report=lambda *a, **k: None,
        ),
    )
    monkeypatch.setattr(sim.asyncio, "run", lambda _: "report")
    monkeypatch.setattr(sim, "_dispatch_webhook", fake_dispatch)
    monkeypatch.setattr(sim, "_post_webhook_via_asgi", lambda *a, **k: (200, "{}"))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "simulate_checkr_webhook.py",
            "--env",
            "beta",
            "--env-file",
            str(env_path),
            "--email",
            "johnsmith@example.com",
            "--result",
            "clear",
            "--force-prod",
            "--yes",
            "--sig-format",
            "sha256",
        ],
    )

    sim.main()

    assert sent["signature"].startswith("sha256=")
