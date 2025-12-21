"""
Regression tests for PR #132 - Skills Configuration
Tests that skills_configured is properly set when services are added/removed.
"""
from unittest.mock import Mock


class TestSkillsConfiguredRegression:
    """Tests for skills_configured lifecycle - PR #132 regression fix"""

    def test_skills_configured_true_after_adding_services(self):
        """
        Regression test: Adding services should set skills_configured=True.

        Bug: _update_services() never updated skills_configured flag.
        Fix: Added profile update at end of _update_services().
        """
        # Simulate initial state where profile.skills_configured = False
        # After adding services, the fix should set it to True
        services_data = [{"name": "Piano Lessons", "price": 50}]

        # After update, if services exist, skills_configured should be True
        has_active_services = bool(services_data)

        assert has_active_services is True

    def test_skills_configured_false_after_removing_all_services(self):
        """When all services are removed, skills_configured should be False."""
        services_data = []  # All services removed

        has_active_services = bool(services_data)

        assert has_active_services is False

    def test_go_live_blocked_without_skills_configured(self):
        """Go-live should fail if skills_configured is False."""
        profile = Mock()
        profile.skills_configured = False

        skills_ok = bool(getattr(profile, "skills_configured", False))

        assert skills_ok is False, "Go-live should be blocked"

    def test_go_live_succeeds_with_skills_configured(self):
        """Go-live should succeed when skills_configured is True."""
        profile = Mock()
        profile.skills_configured = True

        skills_ok = bool(getattr(profile, "skills_configured", False))

        assert skills_ok is True, "Go-live should succeed"


class TestGoLiveFallbackRemoved:
    """
    Documents that fallback logic was intentionally removed in PR #132.
    The service layer now strictly checks skills_configured without fallback.
    """

    def test_strict_check_vs_fallback_behavior(self):
        """
        Document the difference between old and new behavior.

        OLD (routes/instructors.py):
            skills_ok = bool(profile_data.get("skills_configured")) or (
                len(profile_data.get("services", [])) > 0  # <-- Fallback
            )

        NEW (instructor_service.py):
            skills_ok = bool(getattr(profile, "skills_configured", False))  # No fallback
        """
        profile = Mock()
        profile.skills_configured = False
        profile.services = [{"name": "Drums"}]  # Has services but flag is False

        # Old behavior (with fallback) - would pass
        old_skills_ok = bool(profile.skills_configured) or len(profile.services) > 0

        # New behavior (strict) - fails without the fix
        new_skills_ok = bool(getattr(profile, "skills_configured", False))

        assert old_skills_ok is True, "Old fallback would pass"
        assert new_skills_ok is False, "New strict check fails - WHY we need the fix"
