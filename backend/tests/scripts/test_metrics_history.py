import json
from pathlib import Path


def test_metrics_history_git_commits_monotonic():
    history_path = Path(__file__).resolve().parents[3] / "metrics_history.json"
    data = json.loads(history_path.read_text())
    prev = 0
    for entry in data:
        commits = int(entry["git_commits"])
        assert commits >= prev, (
            f"metrics_history.json regress: git_commits {commits} < previous {prev}"
        )
        prev = commits
