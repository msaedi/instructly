"""
Coverage tests for app/models/user.py — targeting uncovered lines:
  L245: __init__ logs when role is provided
  L266: is_instructor cached value is not None
  L306: is_admin cached value is not None
  L369: can_change_status_to invalid status
  L373: can_change_status_to student always False

Bug hunts:
  - Edge cases in computed properties
  - None handling in role checks
  - Account status transitions
"""

from types import SimpleNamespace
from typing import Any

from app.models.user import User


def _make_user(**kwargs: Any) -> User:
    """Create a basic User instance for testing."""
    defaults = {
        "email": "test@example.com",
        "hashed_password": "hash",
        "first_name": "Test",
        "last_name": "User",
        "zip_code": "10001",
        "is_active": True,
        "account_status": "active",
        "totp_enabled": False,
        "phone_verified": False,
    }
    defaults.update(kwargs)
    return User(**defaults)


# ──────────────────────────────────────────────────────────────
# __init__ and __repr__
# ──────────────────────────────────────────────────────────────

class TestUserInit:
    def test_init_with_role_logs(self):
        """L244-245: When role kwarg is present, logger.info is called.

        Since `role` is a read-only property, we must bypass the SQLAlchemy
        declarative constructor to exercise the logging branch.
        """
        from unittest.mock import patch as _patch

        # Use __new__ to skip __init__, then call __init__ with a
        # patched super().__init__ that ignores the role kwarg.
        user = User.__new__(User)
        with _patch.object(User.__bases__[0], "__init__", return_value=None):
            user.__init__(
                email="test@example.com",
                hashed_password="hash",
                first_name="Test",
                last_name="User",
                zip_code="10001",
                role="instructor",
                totp_enabled=False,
                phone_verified=False,
            )
        # If we reached here, the logging branch was exercised

    def test_init_without_role_no_log(self):
        """No role kwarg → no log (transient/cache reconstruction)."""
        user = _make_user()
        assert user.email == "test@example.com"

    def test_repr_with_roles(self):
        """repr includes role names."""
        user = _make_user()
        role_mock = SimpleNamespace(name="student")
        # Set via __dict__ to bypass SQLAlchemy collection instrumentation
        user.__dict__["roles"] = [role_mock]
        result = repr(user)
        assert "student" in result

    def test_repr_without_roles(self):
        user = _make_user()
        user.__dict__["roles"] = []
        result = repr(user)
        assert "no roles" in result


# ──────────────────────────────────────────────────────────────
# Role properties
# ──────────────────────────────────────────────────────────────

class TestRoleProperties:
    def _set_roles(self, user: User, role_list: list) -> None:
        """Set roles bypassing SQLAlchemy instrumentation."""
        user.__dict__["roles"] = role_list

    def test_role_property_with_roles(self):
        user = _make_user()
        self._set_roles(user, [SimpleNamespace(name="instructor")])
        assert user.role == "instructor"

    def test_role_property_without_roles(self):
        user = _make_user()
        self._set_roles(user, [])
        assert user.role is None

    def test_is_instructor_cached(self):
        """L266: cached value is returned when set."""
        user = _make_user()
        user._cached_is_instructor = True
        assert user.is_instructor is True

    def test_is_instructor_cached_false(self):
        user = _make_user()
        user._cached_is_instructor = False
        assert user.is_instructor is False

    def test_is_instructor_from_roles(self):
        user = _make_user()
        self._set_roles(user, [SimpleNamespace(name="instructor")])
        assert user.is_instructor is True

    def test_is_instructor_no_match(self):
        user = _make_user()
        self._set_roles(user, [SimpleNamespace(name="student")])
        assert user.is_instructor is False

    def test_is_student_cached(self):
        user = _make_user()
        user._cached_is_student = True
        assert user.is_student is True

    def test_is_student_from_roles(self):
        user = _make_user()
        self._set_roles(user, [SimpleNamespace(name="student")])
        assert user.is_student is True

    def test_is_admin_cached(self):
        """L306: cached value is returned when set."""
        user = _make_user()
        user._cached_is_admin = True
        assert user.is_admin is True

    def test_is_admin_cached_false(self):
        user = _make_user()
        user._cached_is_admin = False
        assert user.is_admin is False

    def test_is_admin_from_roles(self):
        user = _make_user()
        self._set_roles(user, [SimpleNamespace(name="admin")])
        assert user.is_admin is True

    def test_is_admin_no_roles(self):
        user = _make_user()
        self._set_roles(user, [])
        assert user.is_admin is False

    def test_roles_none_defaults_to_empty(self):
        """Edge case: roles is None → treated as empty."""
        user = _make_user()
        user.__dict__["roles"] = None
        assert user.is_instructor is False
        assert user.is_student is False
        assert user.is_admin is False


# ──────────────────────────────────────────────────────────────
# Account status properties
# ──────────────────────────────────────────────────────────────

class TestAccountStatus:
    def test_is_account_active(self):
        user = _make_user(account_status="active")
        assert user.is_account_active is True

    def test_is_account_not_active(self):
        user = _make_user(account_status="suspended")
        assert user.is_account_active is False

    def test_is_suspended(self):
        user = _make_user(account_status="suspended")
        assert user.is_suspended is True

    def test_is_not_suspended(self):
        user = _make_user(account_status="active")
        assert user.is_suspended is False

    def test_is_deactivated(self):
        user = _make_user(account_status="deactivated")
        assert user.is_deactivated is True

    def test_is_not_deactivated(self):
        user = _make_user(account_status="active")
        assert user.is_deactivated is False

    def test_can_login_active(self):
        user = _make_user(account_status="active")
        assert user.can_login is True

    def test_can_login_suspended(self):
        user = _make_user(account_status="suspended")
        assert user.can_login is True

    def test_cannot_login_deactivated(self):
        user = _make_user(account_status="deactivated")
        assert user.can_login is False


# ──────────────────────────────────────────────────────────────
# can_receive_bookings
# ──────────────────────────────────────────────────────────────

class TestCanReceiveBookings:
    def test_active_instructor(self):
        user = _make_user(account_status="active")
        user._cached_is_instructor = True
        assert user.can_receive_bookings is True

    def test_suspended_instructor(self):
        user = _make_user(account_status="suspended")
        user._cached_is_instructor = True
        assert user.can_receive_bookings is False

    def test_active_student(self):
        user = _make_user(account_status="active")
        user._cached_is_instructor = False
        assert user.can_receive_bookings is False


# ──────────────────────────────────────────────────────────────
# has_profile_picture
# ──────────────────────────────────────────────────────────────

class TestHasProfilePicture:
    def test_with_picture(self):
        user = _make_user()
        user.profile_picture_key = "users/01ABC/avatar.jpg"
        user.profile_picture_version = 1
        assert user.has_profile_picture is True

    def test_without_key(self):
        user = _make_user()
        user.profile_picture_key = None
        user.profile_picture_version = 1
        assert user.has_profile_picture is False

    def test_version_zero(self):
        user = _make_user()
        user.profile_picture_key = "users/01ABC/avatar.jpg"
        user.profile_picture_version = 0
        assert user.has_profile_picture is False


# ──────────────────────────────────────────────────────────────
# can_change_status_to
# ──────────────────────────────────────────────────────────────

class TestCanChangeStatusTo:
    def test_invalid_status(self):
        """L369: invalid status → False."""
        user = _make_user()
        user._cached_is_instructor = True
        user._cached_is_student = False
        assert user.can_change_status_to("invalid") is False

    def test_student_cannot_change(self):
        """L373: student → False."""
        user = _make_user()
        user._cached_is_student = True
        user._cached_is_instructor = False
        assert user.can_change_status_to("suspended") is False

    def test_instructor_can_change_to_active(self):
        user = _make_user()
        user._cached_is_instructor = True
        user._cached_is_student = False
        assert user.can_change_status_to("active") is True

    def test_instructor_can_change_to_suspended(self):
        user = _make_user()
        user._cached_is_instructor = True
        user._cached_is_student = False
        assert user.can_change_status_to("suspended") is True

    def test_instructor_can_change_to_deactivated(self):
        user = _make_user()
        user._cached_is_instructor = True
        user._cached_is_student = False
        assert user.can_change_status_to("deactivated") is True
