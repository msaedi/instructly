
import scripts.prep_db as prep_db


def test_clear_cache_preview_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("RENDER_API_KEY", "dummy")
    calls = []
    monkeypatch.setattr(prep_db, "_render_api_request", lambda *args, **kwargs: calls.append((args, kwargs)))
    prep_db.clear_cache("preview", dry_run=True)
    assert calls == []
    captured = capsys.readouterr()
    assert "(dry-run) Would trigger Render job" in captured.out


def test_clear_cache_preview_calls(monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "dummy")
    responses = [
        [
            {"service": {"name": "instainstru-api-preview", "id": "svc-backend"}},
        ],
        {"id": "job-1"},
        [
            {"service": {"name": "redis-preview", "id": "svc-redis"}},
        ],
        {"id": "deploy-1"},
    ]

    def fake_request(url, api_key, method="GET", data=None):
        assert api_key == "dummy"
        return responses.pop(0)

    monkeypatch.setattr(prep_db, "_render_api_request", fake_request)
    prep_db.clear_cache("preview", dry_run=False)
    assert responses == []


def test_clear_cache_stg_local(monkeypatch):
    calls = []

    def fake_check_call(args, **kwargs):
        calls.append((tuple(args), kwargs))

    def fake_run(*args, **kwargs):
        class Result:
            stdout = "CACHE_CLEAR_OK"
            stderr = ""

        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(prep_db.subprocess, "run", fake_run)
    prep_db.clear_cache("stg", dry_run=False)
    assert calls


def test_clear_cache_missing_key(monkeypatch, capsys):
    monkeypatch.delenv("RENDER_API_KEY", raising=False)
    prep_db.clear_cache("prod", dry_run=False)
    captured = capsys.readouterr()
    assert "RENDER_API_KEY not set" in captured.err or "RENDER_API_KEY not set" in captured.out


def test_clear_cache_service_missing(monkeypatch, capsys):
    monkeypatch.setenv("RENDER_API_KEY", "dummy")

    def fake_request(url, api_key, method="GET", data=None):
        if method == "GET":
            return []
        return {}

    monkeypatch.setattr(prep_db, "_render_api_request", fake_request)
    prep_db.clear_cache("prod", dry_run=False)
    captured = capsys.readouterr()
    assert "Could not find Render service" in captured.err or "Could not find Render service" in captured.out
