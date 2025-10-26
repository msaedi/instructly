from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest
from scripts import backfill_badges as cli


class DummySession:
    def __init__(self):
        self.commit_calls = 0
        self.closed = False
        self.bind = SimpleNamespace(url="postgres://user:pass@localhost:5432/test_db")

    def commit(self):
        self.commit_calls += 1

    def close(self):
        self.closed = True


class FakeBadgeRepository:
    def __init__(self, holder: dict):
        self.holder = holder
        self.transaction_calls = 0

    def transaction(self):
        @contextmanager
        def _ctx():
            self.transaction_calls += 1
            yield
            session = self.holder.get("session")
            if session:
                session.commit()

        return _ctx()


@pytest.fixture
def cli_setup(monkeypatch):
    holder: dict[str, object] = {
        "badge_return": lambda _sid: {field: 0 for field in cli.SUMMARY_FIELDS},
    }

    def session_factory():
        session = DummySession()
        holder["session"] = session
        return session

    class FakeFactory:
        def __init__(self):
            self.user_repo = None

        def create_user_repository(self, db):
            return self.user_repo

    factory = FakeFactory()
    badge_repo = FakeBadgeRepository(holder)
    holder["badge_repo"] = badge_repo

    class FakeBadgeService:
        def __init__(self, db):
            self.repository = badge_repo
            self.calls = []
            holder["service_instance"] = self

        def backfill_user_badges(self, student_id, now_utc, **kwargs):
            result = holder["badge_return"](student_id)
            self.calls.append({"student_id": student_id, **kwargs})
            return result

    def import_stub():
        return session_factory, factory, FakeBadgeService

    monkeypatch.setattr(cli, "_import_dependencies", import_stub)
    holder["factory"] = factory
    return holder


def test_single_user_dry_run(monkeypatch, cli_setup, capsys):
    fake_user = SimpleNamespace(id="user-1")

    class FakeRepo:
        def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return fake_user

        def list_students_paginated(self, **kwargs):
            return []

    repo = FakeRepo()
    cli_setup["factory"].user_repo = repo
    cli_setup["badge_return"] = lambda _sid: {
        "milestones": 2,
        "streak": 1,
        "explorer": 0,
        "quality_pending": 0,
        "skipped_existing": 3,
    }

    exit_code = cli.main(["--user-id", "user-1"])
    assert exit_code == 0

    stdout = capsys.readouterr().out.strip().splitlines()
    assert stdout[0].startswith("[chunk]")
    final_summary = json.loads(stdout[-1])
    assert final_summary["processed_users"] == 1
    assert final_summary["milestones"] == 2
    assert final_summary["streak"] == 1
    assert final_summary["skipped_existing"] == 3
    assert final_summary["dry_run"] is True
    assert final_summary["send_notifications"] is False

    service = cli_setup["service_instance"]
    assert service.calls[0]["student_id"] == "user-1"
    assert service.calls[0]["dry_run"] is True
    assert service.calls[0]["send_notifications"] is False
    assert cli_setup["session"].commit_calls == 0


def test_paginated_run_with_max_users(monkeypatch, cli_setup, capsys):
    students = [SimpleNamespace(id=f"user-{idx}") for idx in range(5)]

    class FakeRepo:
        def __init__(self):
            self.calls = []

        def get_by_id(self, user_id: str):
            return None

        def list_students_paginated(self, *, limit, offset, **kwargs):
            self.calls.append({"limit": limit, "offset": offset})
            return students[offset : offset + limit]

    repo = FakeRepo()
    cli_setup["factory"].user_repo = repo
    cli_setup["badge_return"] = lambda _sid: {
        "milestones": 1,
        "streak": 0,
        "explorer": 0,
        "quality_pending": 0,
        "skipped_existing": 0,
    }

    exit_code = cli.main(["--limit", "2", "--max-users", "3", "--no-dry-run"])
    assert exit_code == 0

    stdout = capsys.readouterr().out.strip().splitlines()
    chunk_lines = [line for line in stdout if line.startswith("[chunk]")]
    assert len(chunk_lines) == 2
    summary = json.loads(stdout[-1])
    assert summary["processed_users"] == 3
    assert summary["milestones"] == 3
    assert summary["dry_run"] is False

    assert repo.calls == [{"limit": 2, "offset": 0}, {"limit": 1, "offset": 2}]
    processed_ids = [call["student_id"] for call in cli_setup["service_instance"].calls]
    assert processed_ids == ["user-0", "user-1", "user-2"]
    assert cli_setup["session"].commit_calls == 2


def test_send_notifications_flag(monkeypatch, cli_setup, capsys):
    fake_user = SimpleNamespace(id="student-77")

    class FakeRepo:
        def get_by_id(self, user_id: str):
            return fake_user

        def list_students_paginated(self, **kwargs):
            return []

    cli_setup["factory"].user_repo = FakeRepo()
    cli_setup["badge_return"] = lambda _sid: {field: 0 for field in cli.SUMMARY_FIELDS}

    exit_code = cli.main(["--user-id", "student-77", "--send-notifications"])
    assert exit_code == 0

    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["send_notifications"] is True
    service = cli_setup["service_instance"]
    assert service.calls[0]["send_notifications"] is True


def test_env_file_and_dsn_flags(monkeypatch, capsys):
    loaded_paths = []
    monkeypatch.setattr(
        cli,
        "load_dotenv",
        lambda path, override=True: loaded_paths.append((str(path), override)) or True,
    )
    applied = []
    monkeypatch.setattr(cli, "_apply_dsn_override", lambda dsn: applied.append(dsn))

    summary_payload = {"processed_users": 0, "dry_run": True, "send_notifications": False}
    for field in cli.SUMMARY_FIELDS:
        summary_payload[field] = 0

    monkeypatch.setattr(cli, "run", lambda args: summary_payload)

    exit_code = cli.main(
        [
            "--user-id",
            "abc",
            "--env-file",
            "/tmp/custom.env",
            "--dsn",
            "postgres://user:pass@db.example.com/db",
        ]
    )
    assert exit_code == 0
    assert loaded_paths[-1][0].endswith("custom.env")
    assert applied == ["postgres://user:pass@db.example.com/db"]
