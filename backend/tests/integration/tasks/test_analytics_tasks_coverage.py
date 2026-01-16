from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.tasks.analytics as analytics


def _set_task_request(task, retries: int = 0) -> None:
    task.request = SimpleNamespace(id="task-123", retries=retries)


def _patch_get_db(monkeypatch, db) -> None:
    monkeypatch.setattr(analytics, "get_db", lambda: iter([db]))


def test_calculate_analytics_success(db, monkeypatch) -> None:
    _set_task_request(analytics.calculate_analytics)
    _patch_get_db(monkeypatch, db)

    calculator = MagicMock()
    calculator.calculate_all_analytics.return_value = 3
    calculator.generate_report.return_value = {"ok": True}

    monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

    result = analytics.calculate_analytics.run(days_back=7)

    assert result["status"] == "success"
    assert result["services_updated"] == 3
    calculator.calculate_all_analytics.assert_called_once_with(days_back=7)
    calculator.update_search_counts.assert_called_once()
    calculator.generate_report.assert_called_once()


def test_calculate_analytics_retries_on_error(db, monkeypatch) -> None:
    _set_task_request(analytics.calculate_analytics, retries=1)
    _patch_get_db(monkeypatch, db)

    calculator = MagicMock()
    calculator.calculate_all_analytics.side_effect = RuntimeError("boom")
    monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

    with patch.object(
        analytics.calculate_analytics, "retry", side_effect=RuntimeError("retry")
    ) as mock_retry:
        with pytest.raises(RuntimeError, match="retry"):
            analytics.calculate_analytics.run(days_back=1)

    assert mock_retry.call_args.kwargs["countdown"] == 120
    assert mock_retry.call_args.kwargs["max_retries"] == 3


def test_generate_daily_report_success(db, monkeypatch) -> None:
    _set_task_request(analytics.generate_daily_report)
    _patch_get_db(monkeypatch, db)

    calculator = MagicMock()
    calculator.generate_report.return_value = {"summary": "ok"}
    monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

    result = analytics.generate_daily_report.run()

    assert result["status"] == "success"
    assert result["report"]["summary"] == "ok"


def test_generate_daily_report_retries_on_error(db, monkeypatch) -> None:
    _set_task_request(analytics.generate_daily_report)
    _patch_get_db(monkeypatch, db)

    calculator = MagicMock()
    calculator.generate_report.side_effect = RuntimeError("boom")
    monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

    with patch.object(
        analytics.generate_daily_report, "retry", side_effect=RuntimeError("retry")
    ) as mock_retry:
        with pytest.raises(RuntimeError, match="retry"):
            analytics.generate_daily_report.run()

    assert mock_retry.call_args.kwargs["countdown"] == 300


def test_update_service_metrics_success(db, monkeypatch) -> None:
    _set_task_request(analytics.update_service_metrics)
    _patch_get_db(monkeypatch, db)

    calculator = MagicMock()
    calculator.calculate_booking_stats.return_value = {"count_7d": 1, "count_30d": 2}
    calculator.calculate_instructor_stats.return_value = {
        "active_instructors": 2,
        "total_weekly_hours": 5,
    }
    monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

    catalog_repo = MagicMock()
    catalog_repo.get_by_id.return_value = SimpleNamespace(id="svc-1")
    analytics_repo = MagicMock()
    analytics_repo.get_or_create.return_value = MagicMock()
    analytics_repo.update.return_value = SimpleNamespace(id="svc-1")

    with patch(
        "app.repositories.factory.RepositoryFactory.create_service_catalog_repository",
        return_value=catalog_repo,
    ), patch(
        "app.repositories.factory.RepositoryFactory.create_service_analytics_repository",
        return_value=analytics_repo,
    ):
        result = analytics.update_service_metrics.run("svc-1")

    assert result["status"] == "success"
    assert result["updated"] is True
    analytics_repo.get_or_create.assert_called_once_with("svc-1")


def test_update_service_metrics_service_missing(db, monkeypatch) -> None:
    _set_task_request(analytics.update_service_metrics)
    _patch_get_db(monkeypatch, db)

    calculator = MagicMock()
    monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

    catalog_repo = MagicMock()
    catalog_repo.get_by_id.return_value = None

    with patch(
        "app.repositories.factory.RepositoryFactory.create_service_catalog_repository",
        return_value=catalog_repo,
    ):
        result = analytics.update_service_metrics.run("missing")

    assert result["status"] == "error"


def test_record_task_execution_smoke(db, monkeypatch) -> None:
    _set_task_request(analytics.record_task_execution)
    _patch_get_db(monkeypatch, db)

    analytics.record_task_execution.run(
        "app.tasks.analytics.calculate_analytics",
        "success",
        1.23,
        result={"ok": True},
        error=None,
    )


def test_record_task_execution_handles_failure(monkeypatch) -> None:
    monkeypatch.setattr(analytics, "get_db", lambda: iter([]))
    _set_task_request(analytics.record_task_execution)

    analytics.record_task_execution.run(
        "app.tasks.analytics.calculate_analytics",
        "error",
        0.5,
        result=None,
        error="boom",
    )
