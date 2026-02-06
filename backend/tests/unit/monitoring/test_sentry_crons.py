from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

import app.monitoring.sentry_crons as sentry_crons


def test_critical_monitor_configs_have_required_fields() -> None:
    for slug, config in sentry_crons.CRITICAL_BEAT_MONITOR_CONFIGS.items():
        assert isinstance(slug, str)
        assert "schedule" in config
        schedule = config["schedule"]
        assert "type" in schedule
        assert "value" in schedule
        assert "timezone" in config
        assert "checkin_margin" in config
        assert "max_runtime" in config
        assert "failure_issue_threshold" in config
        assert "recovery_threshold" in config


def test_monitor_if_configured_returns_identity_when_monitor_missing(monkeypatch) -> None:
    monkeypatch.setattr(sentry_crons, "_monitor", None)

    def sample() -> str:
        return "ok"

    wrapped = sentry_crons.monitor_if_configured("apply-data-retention-policies")(sample)
    assert wrapped is sample
    assert wrapped() == "ok"


def test_monitor_if_configured_returns_identity_when_slug_missing(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_monitor(monitor_slug: str, monitor_config: dict[str, object]):
        calls.append((monitor_slug, monitor_config))

        def decorator(fn):
            return fn

        return decorator

    monkeypatch.setattr(sentry_crons, "_monitor", fake_monitor)

    def sample() -> str:
        return "ok"

    wrapped = sentry_crons.monitor_if_configured("missing-slug")(sample)
    assert wrapped is sample
    assert calls == []


def test_monitor_if_configured_uses_monitor_when_available(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_monitor(monitor_slug: str, monitor_config: dict[str, object]):
        captured["slug"] = monitor_slug
        captured["config"] = monitor_config

        def decorator(fn):
            def wrapper(*args, **kwargs):
                return fn(*args, **kwargs)

            wrapper._wrapped = fn
            return wrapper

        return decorator

    monkeypatch.setattr(sentry_crons, "_monitor", fake_monitor)

    def sample() -> str:
        return "ok"

    wrapped = sentry_crons.monitor_if_configured("apply-data-retention-policies")(sample)
    assert wrapped() == "ok"
    assert captured["slug"] == "apply-data-retention-policies"
    assert captured["config"] is sentry_crons.CRITICAL_BEAT_MONITOR_CONFIGS[
        "apply-data-retention-policies"
    ]


def _extract_monitor_slug(task) -> str | None:
    run_fn = task.__class__.run
    if run_fn.__closure__ is None:
        return None
    for cell in run_fn.__closure__:
        monitor_obj = cell.cell_contents
        slug = getattr(monitor_obj, "monitor_slug", None)
        if slug:
            return slug
    return None


def test_critical_tasks_are_decorated() -> None:
    if sentry_crons._monitor is None:
        pytest.skip("sentry_sdk not installed; monitor decorator unavailable")

    task_mappings = [
        ("app.tasks.privacy_tasks", "apply_retention_policies", "apply-data-retention-policies"),
        ("app.tasks.search_analytics", "calculate_search_metrics", "calculate-search-metrics"),
        ("app.tasks.location_learning", "process_location_learning", "learn-location-aliases"),
        ("app.tasks.payment_tasks", "resolve_undisputed_no_shows", "resolve-undisputed-no-shows"),
        # Fast-completing tasks (GitHub #2651 workaround)
        ("app.tasks.privacy_tasks", "cleanup_search_history", "cleanup-search-history"),
        (
            "app.tasks.embedding_migration",
            "maintain_service_embeddings",
            "maintain-service-embeddings",
        ),
        (
            "app.tasks.referral_tasks",
            "retry_failed_instructor_referral_payouts",
            "retry-failed-instructor-referral-payouts",
        ),
        ("app.tasks.payment_tasks", "capture_completed_lessons", "capture-completed-lessons"),
        (
            "app.tasks.codebase_metrics",
            "append_history",
            "append-codebase-metrics-history",
        ),
        ("app.tasks.retention_tasks", "purge_soft_deleted_task", "nightly-retention-purge"),
        ("app.tasks.celery_app", "run_availability_retention", "availability-retention-daily"),
    ]

    for module_name, task_attr, slug in task_mappings:
        module = importlib.import_module(module_name)
        task = getattr(module, task_attr)
        assert _extract_monitor_slug(task) == slug, f"{module_name}.{task_attr} missing monitor"


def test_excludes_count_matches_configs() -> None:
    assert len(sentry_crons.CRITICAL_BEAT_MONITOR_EXCLUDES) == len(
        sentry_crons.CRITICAL_BEAT_MONITOR_CONFIGS
    )


def test_slugs_tuple_matches_config_keys() -> None:
    assert set(sentry_crons.CRITICAL_BEAT_MONITOR_SLUGS) == set(
        sentry_crons.CRITICAL_BEAT_MONITOR_CONFIGS.keys()
    )


@pytest.mark.parametrize(
    "task_name,should_exclude",
    [
        ("cleanup-search-history", True),
        ("maintain-service-embeddings", True),
        ("retry-failed-instructor-referral-payouts", True),
        ("capture-completed-lessons", True),
        ("apply-data-retention-policies", True),
        ("append-codebase-metrics-history", True),
        ("nightly-retention-purge", True),
        ("availability-retention-daily", True),
        ("some-other-task", False),
        ("notifications-dispatch-pending", False),
    ],
)
def test_exclude_pattern_matching(task_name: str, should_exclude: bool) -> None:
    import re

    matches = any(
        re.match(pattern, task_name)
        for pattern in sentry_crons.CRITICAL_BEAT_MONITOR_EXCLUDES
    )
    assert matches == should_exclude, (
        f"{task_name} should {'be' if should_exclude else 'not be'} excluded"
    )


def test_task_executes_with_monitor_wrapper(monkeypatch) -> None:
    module = importlib.import_module("app.tasks.location_learning")

    mock_db = MagicMock()
    monkeypatch.setattr(module, "get_db", lambda: iter([mock_db]))

    mock_service = MagicMock()
    mock_service.process_pending.return_value = []
    monkeypatch.setattr(module, "AliasLearningService", lambda _db: mock_service)

    result = module.process_location_learning.run(limit=25)
    assert result["status"] == "success"
    mock_service.process_pending.assert_called_once_with(limit=25)
