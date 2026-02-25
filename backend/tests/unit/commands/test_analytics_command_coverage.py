"""
Coverage tests for app/commands/analytics.py — targeting uncovered lines:
  L300-301: main() with 'run' that returns success including report

Bug hunts:
  - Command execution failure
  - Report display edge cases
"""

from __future__ import annotations

from unittest.mock import MagicMock

import app.commands.analytics as analytics_mod


class TestMainRunWithReport:
    def test_main_run_success_with_report(self, monkeypatch, capsys):
        """L300-301: run command returns success with report → prints report summary."""
        runner = MagicMock()
        runner.run_analytics.return_value = {
            "status": "success",
            "execution_time": 2.5,
            "services_updated": 10,
            "report": {"top_services": ["yoga", "piano"], "total_bookings": 150},
        }

        monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
        monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "run"])

        analytics_mod.main()
        out = capsys.readouterr().out
        assert "Analytics completed successfully" in out
        assert "Report Summary" in out
        assert "yoga" in out

    def test_main_run_success_without_report(self, monkeypatch, capsys):
        """Run returns success without report key → no report section."""
        runner = MagicMock()
        runner.run_analytics.return_value = {
            "status": "success",
            "execution_time": 1.0,
            "services_updated": 3,
        }

        monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
        monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "run", "--days", "30"])

        analytics_mod.main()
        out = capsys.readouterr().out
        assert "Analytics completed successfully" in out
        assert "Report Summary" not in out

    def test_main_status_completed_not_yet(self, monkeypatch, capsys):
        """Status with completed_at == 'Not completed' → not printed."""
        runner = MagicMock()
        runner.check_status.return_value = {
            "last_run": {
                "started_at": "2025-01-01T00:00:00",
                "completed_at": "Not completed",
                "status": "running",
            },
        }

        monkeypatch.setattr(analytics_mod, "AnalyticsCommand", lambda: runner)
        monkeypatch.setattr(analytics_mod.sys, "argv", ["analytics", "status"])

        analytics_mod.main()
        out = capsys.readouterr().out
        assert "running" in out
        # "Completed:" should not appear when it's "Not completed"
        assert "Completed:" not in out
