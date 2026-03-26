import json
from pathlib import Path


def test_backend_ci_uses_shared_pip_audit_runner():
    repo_root = Path(__file__).resolve().parents[2]
    workflow = repo_root / ".github" / "workflows" / "backend-ci.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "bash scripts/run_pip_audit.sh --desc" in content


def test_pip_audit_ignore_tracks_temporary_pygments_exception():
    backend_root = Path(__file__).resolve().parents[1]
    ignore_file = backend_root / "pip-audit.ignore.json"
    payload = json.loads(ignore_file.read_text(encoding="utf-8"))

    assert "GHSA-5239-wwwm-4pmq" in payload["ignore"]
