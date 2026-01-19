from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import settings
from app.routes.v1 import beta as beta_routes


class TestBetaRoutesAdditionalCoverage:
    def test_metrics_summary_prometheus(self, client: TestClient, auth_headers_admin, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_http_url", "http://example.com")
        monkeypatch.setattr(settings, "prometheus_bearer_token", "token")

        def _fake_get(_url, params=None, headers=None, timeout=None):
            query = (params or {}).get("query", "")
            if "status=\"success\"" in query:
                val = 3
            elif "status=\"error\"" in query:
                val = 1
            elif "phase=\"open_beta\"" in query:
                val = 5
            else:
                val = 0

            class R:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"data": {"result": [{"value": [0, str(val)]}]}}

            return R()

        monkeypatch.setattr(beta_routes.requests, "get", _fake_get)

        res = client.get("/api/v1/beta/metrics/summary", headers=auth_headers_admin)
        assert res.status_code == 200
        data = res.json()
        assert data["invites_sent_24h"] == 3
        assert data["invites_errors_24h"] == 1
        assert data["phase_counts_24h"].get("open_beta") == 5

    def test_metrics_summary_fallback(self, client: TestClient, auth_headers_admin, monkeypatch):
        monkeypatch.setattr(settings, "prometheus_http_url", "")

        metrics = (
            "instainstru_service_operations_total{operation=\"beta_invite_sent\",status=\"success\"} 2\n"
            "instainstru_service_operations_total{operation=\"beta_invite_sent\",status=\"error\"} 1\n"
            "instainstru_beta_phase_header_total{phase=\"instructor_only\"} 4\n"
        )
        monkeypatch.setattr(beta_routes.prometheus_metrics, "get_metrics", lambda: metrics.encode("utf-8"))

        res = client.get("/api/v1/beta/metrics/summary", headers=auth_headers_admin)
        assert res.status_code == 200
        data = res.json()
        assert data["invites_sent_24h"] == 2
        assert data["invites_errors_24h"] == 1
        assert data["phase_counts_24h"].get("instructor_only") == 4

    def test_send_invite_batch_and_async(self, client: TestClient, auth_headers_admin, monkeypatch):
        sent = [
            (SimpleNamespace(id="inv1", code="CODE1"), "a@example.com", "join", "welcome"),
        ]
        failed = [("b@example.com", "error")]

        monkeypatch.setattr(
            beta_routes.BetaService,
            "send_invite_batch",
            lambda *_args, **_kwargs: (sent, failed),
        )

        res = client.post(
            "/api/v1/beta/invites/send-batch",
            headers=auth_headers_admin,
            json={
                "emails": ["a@example.com", "b@example.com"],
                "role": "instructor_beta",
                "expires_in_days": 7,
                "source": "tests",
                "base_url": "https://example.com",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["sent"][0]["email"] == "a@example.com"
        assert body["failed"][0]["email"] == "b@example.com"

        monkeypatch.setattr(
            beta_routes.celery_app,
            "send_task",
            lambda *_args, **_kwargs: SimpleNamespace(id="task-123"),
        )

        res_async = client.post(
            "/api/v1/beta/invites/send-batch-async",
            headers=auth_headers_admin,
            json={
                "emails": ["a@example.com"],
                "role": "instructor_beta",
                "expires_in_days": 7,
                "source": "tests",
                "base_url": "https://example.com",
            },
        )
        assert res_async.status_code == 200
        assert res_async.json()["task_id"] == "task-123"

    def test_invite_batch_progress_and_validation(self, client: TestClient, auth_headers_admin, monkeypatch):
        res = client.get(
            "/api/v1/beta/invites/send-batch-progress",
            params={"task_id": ""},
            headers=auth_headers_admin,
        )
        assert res.status_code == 422

        class _Result:
            state = "PROGRESS"
            info = {"current": 2, "total": 5, "sent": 2, "failed": 1}

        monkeypatch.setattr(beta_routes.celery_app, "AsyncResult", lambda _task_id: _Result())

        res_ok = client.get(
            "/api/v1/beta/invites/send-batch-progress",
            params={"task_id": "task-123"},
            headers=auth_headers_admin,
        )
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["state"] == "PROGRESS"
        assert data["current"] == 2
        assert data["failed"] == 1

    def test_validate_invite_sets_and_clears_cookie(
        self, client: TestClient, auth_headers_admin, monkeypatch
    ):
        invite = SimpleNamespace(
            code="CODE123",
            email="invitee@example.com",
            role="instructor_beta",
            expires_at=None,
            used_at=None,
        )
        monkeypatch.setattr(
            beta_routes.BetaService,
            "validate_invite",
            lambda *_args, **_kwargs: (True, None, invite),
        )

        res = client.get(
            "/api/v1/beta/invites/validate",
            params={"invite_code": "CODE123"},
            headers=auth_headers_admin,
        )
        assert res.status_code == 200
        assert "set-cookie" in res.headers

        monkeypatch.setattr(
            beta_routes.BetaService,
            "validate_invite",
            lambda *_args, **_kwargs: (False, "invalid", None),
        )
        cookie_name = beta_routes.invite_cookie_name()
        client.cookies.set(cookie_name, "stale")
        res_invalid = client.get(
            "/api/v1/beta/invites/validate",
            params={"invite_code": "CODE123"},
            headers=auth_headers_admin,
        )
        client.cookies.clear()
        assert res_invalid.status_code == 200
        assert cookie_name in res_invalid.headers.get("set-cookie", "")

    def test_invite_verified_requires_cookie(self, client: TestClient):
        res = client.get("/api/v1/beta/invites/verified")
        assert res.status_code == 401

        cookie_name = beta_routes.invite_cookie_name()
        marker = beta_routes._encode_invite_marker("CODE123")
        client.cookies.set(cookie_name, marker)
        res_ok = client.get("/api/v1/beta/invites/verified")
        client.cookies.clear()
        assert res_ok.status_code == 204

    def test_generate_and_consume_invites(self, client: TestClient, auth_headers_admin, monkeypatch, db):
        now = datetime.now(timezone.utc)
        invites = [
            SimpleNamespace(id="inv-1", code="CODE1", email=None, role="student", expires_at=now),
            SimpleNamespace(
                id="inv-2", code="CODE2", email="x@example.com", role="instructor", expires_at=now
            ),
        ]
        monkeypatch.setattr(
            beta_routes.BetaService, "bulk_generate", lambda *_args, **_kwargs: invites
        )

        payload = beta_routes.InviteGenerateRequest(
            count=2,
            role="student",
            expires_in_days=7,
            source="tests",
            emails=["x@example.com", "y@example.com"],
        )
        result = beta_routes.generate_invites(payload, db=db, _admin=None)
        assert len(result.invites) == 2

        grant = SimpleNamespace(
            id="grant-1",
            user_id="user-1",
            role="student",
            phase="open_beta",
            invited_by_code="CODE1",
        )
        monkeypatch.setattr(
            beta_routes.BetaService,
            "consume_and_grant",
            lambda *_args, **_kwargs: (grant, None, None),
        )
        consume = client.post(
            "/api/v1/beta/invites/consume",
            json={"code": "CODE1", "user_id": "user-1", "role": "student", "phase": "open_beta"},
        )
        assert consume.status_code == 200

        monkeypatch.setattr(
            beta_routes.BetaService,
            "consume_and_grant",
            lambda *_args, **_kwargs: (None, "invalid", None),
        )
        consume_fail = client.post(
            "/api/v1/beta/invites/consume",
            json={"code": "BAD", "user_id": "user-1", "role": "student", "phase": "open_beta"},
        )
        assert consume_fail.status_code == 400

    def test_send_invite_and_settings(self, client: TestClient, auth_headers_admin, monkeypatch):
        invite = SimpleNamespace(id="inv-99", code="CODE99")
        monkeypatch.setattr(
            beta_routes.BetaService,
            "send_invite_email",
            lambda *_args, **_kwargs: (invite, "join", "welcome"),
        )

        res = client.post(
            "/api/v1/beta/invites/send",
            headers=auth_headers_admin,
            json={
                "to_email": "invitee@example.com",
                "role": "student",
                "expires_in_days": 7,
                "source": "tests",
                "base_url": "https://example.com",
                "grant_founding_status": False,
            },
        )
        assert res.status_code == 200
        assert res.json()["code"] == "CODE99"

        class DummyRepo:
            def __init__(self, _db):
                pass

            def get_singleton(self):
                return SimpleNamespace(
                    beta_disabled=False,
                    beta_phase="open_beta",
                    allow_signup_without_invite=True,
                )

            def update_settings(self, beta_disabled, beta_phase, allow_signup_without_invite):
                return SimpleNamespace(
                    beta_disabled=beta_disabled,
                    beta_phase=beta_phase,
                    allow_signup_without_invite=allow_signup_without_invite,
                )

        monkeypatch.setattr(beta_routes, "BetaSettingsRepository", DummyRepo)
        invalidations: list[bool] = []
        monkeypatch.setattr(
            beta_routes, "invalidate_beta_settings_cache", lambda: invalidations.append(True)
        )

        res_settings = client.get("/api/v1/beta/settings", headers=auth_headers_admin)
        assert res_settings.status_code == 200
        assert res_settings.json()["beta_phase"] == "open_beta"

        res_update = client.put(
            "/api/v1/beta/settings",
            headers=auth_headers_admin,
            json={
                "beta_disabled": True,
                "beta_phase": "disabled",
                "allow_signup_without_invite": False,
            },
        )
        assert res_update.status_code == 200
        assert invalidations
