import subprocess

import scripts.prep_db as prep_db


def test_clear_cache_stg_dry_run(monkeypatch, capsys):
    called = []

    def fake_run(*args, **kwargs):
        called.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", fake_run)
    prep_db.clear_cache("stg", dry_run=True)
    assert called == []
    captured = capsys.readouterr()
    assert "(dry-run) Would run local cache clear script for STG" in captured.out


def test_clear_cache_stg_success(monkeypatch, capsys):
    recorded = {}

    class Result:
        stdout = "cache ok\nCACHE_CLEAR_OK"
        stderr = ""

    def fake_run(*args, **kwargs):
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    prep_db.clear_cache("stg", dry_run=False)
    captured = capsys.readouterr()
    assert "Local cache cleared successfully" in captured.out
    assert "--echo-sentinel" in recorded["args"][0]


def test_clear_cache_stg_failure(monkeypatch, capsys):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0], stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    prep_db.clear_cache("stg", dry_run=False)
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Local cache clear failed" in combined


def test_clear_cache_stg_missing_script(monkeypatch, capsys):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)
    prep_db.clear_cache("stg", dry_run=False)
    captured = capsys.readouterr()
    assert "clear_cache.py not found" in (captured.out + captured.err)
