import json
from pathlib import Path

from app.schemas.codebase_metrics_models import CodebaseHistoryEntry


def test_metrics_history_git_commits_monotonic():
    history_path = Path(__file__).resolve().parents[3] / "metrics_history.json"
    data = json.loads(history_path.read_text())
    prev = 0
    for entry in data:
        CodebaseHistoryEntry.model_validate(entry)
        commits = int(entry["git_commits"])
        assert commits >= prev, (
            f"metrics_history.json regress: git_commits {commits} < previous {prev}"
        )
        prev = commits
        assert "backend_files" in entry
        assert "frontend_files" in entry
        assert "unique_contributors" in entry
        assert "first_commit_date" in entry
        assert "last_commit_date" in entry
        assert "branch" in entry
