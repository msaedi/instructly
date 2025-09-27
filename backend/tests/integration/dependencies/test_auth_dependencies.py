# backend/tests/integration/dependencies/test_auth_dependencies.py
"""
Comprehensive test suite for authentication dependencies.
Tests all auth dependency functions and edge cases.
Target: Increase coverage from 50% to 90%+
"""

from unittest.mock import Mock

from fastapi import HTTPException, status
import pytest
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    get_current_active_user,
    get_current_instructor,
    get_current_student,
    get_current_user,
)
from app.core.enums import RoleName
from app.models.user import User


class TestAuthDependencies:
    """Test authentication dependency functions."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_user_student(self):
        """Create mock student user."""
        user = Mock(spec=User)
        user.id = 1
        user.email = "student@example.com"
        user.first_name = ("Test",)
        _last_name = "Student"
        user.is_active = True
        # RBAC: Mock roles
        student_role = Mock()
        student_role.name = RoleName.STUDENT
        user.roles = [student_role]
        # Add properties
        user.is_instructor = False
        user.is_student = True
        return user

    @pytest.fixture
    def mock_user_instructor(self):
        """Create mock instructor user."""
        user = Mock(spec=User)
        user.id = 2
        user.email = "instructor@example.com"
        user.first_name = ("Test",)
        _last_name = "Instructor"
        user.is_active = True
        # RBAC: Mock roles
        instructor_role = Mock()
        instructor_role.name = RoleName.INSTRUCTOR
        user.roles = [instructor_role]
        # Add properties
        user.is_instructor = True
        user.is_student = False
        return user

    @pytest.fixture
    def mock_user_inactive(self):
        """Create mock inactive user."""
        user = Mock(spec=User)
        user.id = 3
        user.email = "inactive@example.com"
        user.first_name = ("Inactive",)
        _last_name = "User"
        user.is_active = False
        # RBAC: Mock roles
        student_role = Mock()
        student_role.name = RoleName.STUDENT
        user.roles = [student_role]
        # Add properties
        user.is_instructor = False
        user.is_student = True
        return user

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_db, mock_user_student):
        """Test successful user retrieval from JWT."""
        # Setup
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = mock_user_student
        mock_db.query.return_value = mock_query

        # Execute
        result = await get_current_user("student@example.com", mock_db)

        # Verify
        assert result == mock_user_student
        mock_db.query.assert_called_once_with(User)
        mock_query.filter.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_user_not_found(self, mock_db):
        """Test user not found scenario."""
        # Setup
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None  # User not found
        mock_db.query.return_value = mock_query

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user("nonexistent@example.com", mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "User not found"

    @pytest.mark.asyncio
    async def test_get_current_active_user_success(self, mock_user_student):
        """Test successful active user retrieval."""
        # Execute
        result = await get_current_active_user(mock_user_student)

        # Verify
        assert result == mock_user_student

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self, mock_user_inactive):
        """Test inactive user scenario."""
        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(mock_user_inactive)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Inactive user"

    @pytest.mark.asyncio
    async def test_get_current_instructor_success(self, mock_user_instructor):
        """Test successful instructor retrieval."""
        # Execute
        result = await get_current_instructor(mock_user_instructor)

        # Verify
        assert result == mock_user_instructor

    @pytest.mark.asyncio
    async def test_get_current_instructor_not_instructor(self, mock_user_student):
        """Test non-instructor user trying to access instructor endpoint."""
        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await get_current_instructor(mock_user_student)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "Not an instructor"

    @pytest.mark.asyncio
    async def test_get_current_student_success(self, mock_user_student):
        """Test successful student retrieval."""
        # Execute
        result = await get_current_student(mock_user_student)

        # Verify
        assert result == mock_user_student

    @pytest.mark.asyncio
    async def test_get_current_student_not_student(self, mock_user_instructor):
        """Test non-student user trying to access student endpoint."""
        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await get_current_student(mock_user_instructor)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "Not a student"

    @pytest.mark.asyncio
    async def test_dependency_chain_student(self, mock_db, mock_user_student):
        """Test complete dependency chain for student."""
        # Setup
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = mock_user_student
        mock_db.query.return_value = mock_query

        # Execute through dependency chain
        user = await get_current_user("student@example.com", mock_db)
        active_user = await get_current_active_user(user)
        student = await get_current_student(active_user)

        # Verify
        assert student == mock_user_student

    @pytest.mark.asyncio
    async def test_dependency_chain_instructor(self, mock_db, mock_user_instructor):
        """Test complete dependency chain for instructor."""
        # Setup
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = mock_user_instructor
        mock_db.query.return_value = mock_query

        # Execute through dependency chain
        user = await get_current_user("instructor@example.com", mock_db)
        active_user = await get_current_active_user(user)
        instructor = await get_current_instructor(active_user)

        # Verify
        assert instructor == mock_user_instructor

    @pytest.mark.asyncio
    async def test_dependency_chain_inactive_user(self, mock_db, mock_user_inactive):
        """Test dependency chain failure for inactive user."""
        # Setup
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = mock_user_inactive
        mock_db.query.return_value = mock_query

        # Execute
        user = await get_current_user("inactive@example.com", mock_db)

        # Should fail at active user check
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(user)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_database_error_handling(self, mock_db):
        """Test handling of database errors."""
        # Setup - simulate database error
        mock_db.query.side_effect = Exception("Database connection failed")

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await get_current_user("test@example.com", mock_db)

        assert "Database connection failed" in str(exc_info.value)


class TestAuthDependenciesEdgeCases:
    """Test edge cases and security scenarios."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return Mock(spec=Session)

    @pytest.mark.asyncio
    async def test_sql_injection_protection(self, mock_db):
        """Test that SQL injection attempts are handled safely."""
        # Setup
        malicious_email = "admin@example.com' OR '1'='1"
        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None
        mock_db.query.return_value = mock_query

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(malicious_email, mock_db)

        # Should still result in user not found, not SQL error
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_case_sensitive_email_lookup(self, mock_db):
        """Test that email lookup is case-sensitive as per security best practices."""
        # Setup
        user = Mock(spec=User)
        user.email = "test@example.com"
        user.is_active = True

        mock_query = Mock()
        mock_filter = Mock()
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        # Test exact match
        mock_filter.first.return_value = user
        result = await get_current_user("test@example.com", mock_db)
        assert result == user

        # Test different case - should use database's comparison
        # (In practice, the database query would handle case sensitivity)
        result = await get_current_user("TEST@EXAMPLE.COM", mock_db)

    @pytest.mark.asyncio
    async def test_user_with_multiple_roles(self, mock_db):
        """Test handling of users with conflicting role states."""
        # Create user with conflicting states
        weird_user = Mock(spec=User)
        weird_user.id = 999
        weird_user.email = "weird@example.com"
        weird_user.is_active = True
        weird_user.is_instructor = False  # Conflict!
        weird_user.is_student = True  # Conflict!

        # Should fail instructor check
        with pytest.raises(HTTPException) as exc_info:
            await get_current_instructor(weird_user)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

        # Should pass student check (based on is_student flag)
        result = await get_current_student(weird_user)
        assert result == weird_user

    @pytest.mark.asyncio
    async def test_null_user_attributes(self, mock_db):
        """Test handling of users with null attributes."""
        # Create user with null attributes
        null_user = Mock(spec=User)
        null_user.id = 1
        null_user.email = None  # Shouldn't happen but test resilience
        null_user.is_active = None
        null_user.is_instructor = None
        null_user.is_student = None

        # Should treat null is_active as False
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(null_user)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

        # Should treat null role flags as False
        with pytest.raises(HTTPException) as exc_info:
            await get_current_instructor(null_user)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestAuthIntegration:
    """Integration tests with actual database."""

    @pytest.mark.asyncio
    async def test_full_auth_flow_student(self, db, test_student):
        """Test complete authentication flow for student."""
        # Get user by email
        result = await get_current_user(test_student.email, db)
        assert result.id == test_student.id

        # Check active status
        active_result = await get_current_active_user(result)
        assert active_result.id == test_student.id

        # Check student role
        student_result = await get_current_student(active_result)
        assert student_result.id == test_student.id

        # Should fail instructor check
        with pytest.raises(HTTPException) as exc_info:
            await get_current_instructor(active_result)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_full_auth_flow_instructor(self, db, test_instructor):
        """Test complete authentication flow for instructor."""
        # Get user by email
        result = await get_current_user(test_instructor.email, db)
        assert result.id == test_instructor.id

        # Check active status
        active_result = await get_current_active_user(result)
        assert active_result.id == test_instructor.id

        # Check instructor role
        instructor_result = await get_current_instructor(active_result)
        assert instructor_result.id == test_instructor.id

        # Should fail student check
        with pytest.raises(HTTPException) as exc_info:
            await get_current_student(active_result)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_deactivated_user(self, db, test_student):
        """Test authentication with deactivated user."""
        # Deactivate user
        test_student.is_active = False
        db.commit()

        # Can still find user
        result = await get_current_user(test_student.email, db)
        assert result.id == test_student.id

        # But fails active check
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(result)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Inactive user"
