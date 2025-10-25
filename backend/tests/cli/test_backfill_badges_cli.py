import json
from types import SimpleNamespace

import pytest
from scripts import backfill_badges as cli


class DummySession:
    def __init__(self):
        self.commit_calls = 0
        self.closed = False

    def commit(self):
        self.commit_calls += 1

    def close(self):
        self.closed = True


@pytest.fixture
def session_holder(monkeypatch):
    holder: dict[str, DummySession] = {}

    def factory():
        session = DummySession()
        holder["session"] = session
        return session

    monkeypatch.setattr(cli, "SessionLocal", factory)
    return holder


def test_single_user_dry_run(monkeypatch, session_holder, capsys):
    fake_user = SimpleNamespace(id="user-1")

    class FakeRepo:
        def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return fake_user

        def list_students_paginated(self, **kwargs):
            return []

    repo = FakeRepo()
    monkeypatch.setattr(cli.RepositoryFactory, "create_user_repository", lambda db: repo)

    service_calls = {}

    class FakeBadgeService:
        def __init__(self, db):
            service_calls["instance"] = self
            self.calls = []

        def backfill_user_badges(self, student_id, now_utc, **kwargs):
            self.calls.append({"student_id": student_id, **kwargs})
            return {
                "milestones": 2,
                "streak": 1,
                "explorer": 0,
                "quality_pending": 0,
                "skipped_existing": 3,
            }

    monkeypatch.setattr(cli, "BadgeAwardService", FakeBadgeService)

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

    service = service_calls["instance"]
    assert service.calls[0]["student_id"] == "user-1"
    assert service.calls[0]["dry_run"] is True
    assert service.calls[0]["send_notifications"] is False
    assert session_holder["session"].commit_calls == 0


def test_paginated_run_with_max_users(monkeypatch, session_holder, capsys):
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
    monkeypatch.setattr(cli.RepositoryFactory, "create_user_repository", lambda db: repo)

    call_log = []

    class FakeBadgeService:
        def __init__(self, db):
            self.calls = call_log

        def backfill_user_badges(self, student_id, now_utc, **kwargs):
            self.calls.append({"student_id": student_id, **kwargs})
            return {
                "milestones": 1,
                "streak": 0,
                "explorer": 0,
                "quality_pending": 0,
                "skipped_existing": 0,
            }

    monkeypatch.setattr(cli, "BadgeAwardService", FakeBadgeService)

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
    processed_ids = [call["student_id"] for call in call_log]
    assert processed_ids == ["user-0", "user-1", "user-2"]
    assert session_holder["session"].commit_calls == 2


def test_send_notifications_flag(monkeypatch, session_holder, capsys):
    fake_user = SimpleNamespace(id="student-77")

    class FakeRepo:
        def get_by_id(self, user_id: str):
            return fake_user

        def list_students_paginated(self, **kwargs):
            return []

    monkeypatch.setattr(cli.RepositoryFactory, "create_user_repository", lambda db: FakeRepo())

    captured_kwargs = {}

    class FakeBadgeService:
        def __init__(self, db):
            pass

        def backfill_user_badges(self, student_id, now_utc, **kwargs):
            captured_kwargs.update(kwargs)
            return {field: 0 for field in cli.SUMMARY_FIELDS}

    monkeypatch.setattr(cli, "BadgeAwardService", FakeBadgeService)

    exit_code = cli.main(["--user-id", "student-77", "--send-notifications"])
    assert exit_code == 0

    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["send_notifications"] is True
    assert captured_kwargs["send_notifications"] is True
