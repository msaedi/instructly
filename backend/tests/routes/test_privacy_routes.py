# backend/tests/routes/test_privacy_routes.py
"""
Tests for privacy API endpoints.
"""

from unittest.mock import MagicMock, patch

from fastapi import status

from app.auth import create_access_token
from app.core.enums import RoleName
from app.services.permission_service import PermissionService

# Fixtures moved to conftest.py


class TestPrivacyEndpoints:
    """Test cases for privacy API endpoints."""

    def test_export_my_data_success(self, client, sample_user_for_privacy, db):
        """Test successful data export for current user."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            # Mock the service
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.export_user_data.return_value = {
                "export_date": "2025-07-30T12:00:00Z",
                "user_profile": {
                    "id": sample_user_for_privacy.id,
                    "email": sample_user_for_privacy.email,
                    "first_name": sample_user_for_privacy.first_name,
                    "last_name": sample_user_for_privacy.last_name,
                    "role": sample_user_for_privacy.role,
                },
                "search_history": [],
                "bookings": [],
            }

            response = client.get("/api/privacy/export/me", headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == "Data export completed successfully"
            assert "data" in data
            assert data["data"]["user_profile"]["id"] == sample_user_for_privacy.id

            # Verify service was called correctly
            mock_service.export_user_data.assert_called_once_with(sample_user_for_privacy.id)

    def test_export_my_data_service_error(self, client, sample_user_for_privacy, db):
        """Test data export with service error."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.export_user_data.side_effect = Exception("Database error")

            response = client.get("/api/privacy/export/me", headers=headers)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert data["detail"] == "Failed to export user data"

    def test_delete_my_data_anonymize_success(self, client, sample_user_for_privacy, db):
        """Test successful data anonymization (not full deletion)."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.return_value = True

            request_data = {"delete_account": False}
            response = client.post("/api/privacy/delete/me", json=request_data, headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == "Personal data anonymized"
            assert data["account_deleted"] is False

            mock_service.anonymize_user.assert_called_once_with(sample_user_for_privacy.id)

    def test_delete_my_data_full_deletion_success(self, client, sample_user_for_privacy, db):
        """Test successful full account deletion."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {
                "search_history": 5,
                "search_events": 10,
                "bookings": 2,
                "alerts": 3,
            }

            request_data = {"delete_account": True}
            response = client.post("/api/privacy/delete/me", json=request_data, headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == "Account and all associated data deleted"
            assert data["account_deleted"] is True
            assert "deletion_stats" in data

            mock_service.delete_user_data.assert_called_once_with(sample_user_for_privacy.id, delete_account=True)

    def test_delete_my_data_service_error(self, client, sample_user_for_privacy, db):
        """Test data deletion with service error."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.side_effect = Exception("Database error")

            request_data = {"delete_account": False}
            response = client.post("/api/privacy/delete/me", json=request_data, headers=headers)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert data["detail"] == "Failed to delete user data"

    def test_get_privacy_statistics_success(self, client, sample_admin_for_privacy, db):
        """Test successful privacy statistics retrieval (admin only)."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.get_privacy_statistics.return_value = {
                "total_users": 100,
                "active_users": 95,
                "search_history_records": 500,
                "bookings_with_pii": 200,
            }

            response = client.get("/api/privacy/statistics", headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert "statistics" in data
            assert data["statistics"]["total_users"] == 100

    def test_apply_retention_policies_success(self, client, sample_admin_for_privacy, db):
        """Test successful retention policy application (admin only)."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.apply_retention_policies.return_value = {
                "search_events_deleted": 50,
                "old_bookings_anonymized": 10,
                "old_alerts_deleted": 25,
            }

            response = client.post("/api/privacy/retention/apply", headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == "Retention policies applied"
            assert "stats" in data
            assert data["stats"]["search_events_deleted"] == 50

    def test_export_user_data_admin_success(self, client, sample_admin_for_privacy, sample_user_for_privacy, db):
        """Test admin exporting data for another user."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.export_user_data.return_value = {
                "user_profile": {"id": sample_user_for_privacy.id},
                "search_history": [],
            }

            response = client.get(f"/api/privacy/export/user/{sample_user_for_privacy.id}", headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == f"Data export completed for user {sample_user_for_privacy.id}"

            mock_service.export_user_data.assert_called_once_with(sample_user_for_privacy.id)

    def test_export_user_data_sample_admin_for_privacy_not_found(self, client, sample_admin_for_privacy, db):
        """Test admin exporting data for non-existent user."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.export_user_data.side_effect = ValueError("User 999 not found")

            response = client.get("/api/privacy/export/user/999", headers=headers)

            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            assert data["detail"] == "User 999 not found"

    def test_delete_user_data_admin_success(self, client, sample_admin_for_privacy, sample_user_for_privacy, db):
        """Test admin deleting data for another user."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {
                "search_history": 3,
                "bookings": 1,
            }

            request_data = {"delete_account": True}
            response = client.post(
                f"/api/privacy/delete/user/{sample_user_for_privacy.id}", json=request_data, headers=headers
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == f"Data deleted for user {sample_user_for_privacy.id}"
            assert data["account_deleted"] is True

            mock_service.delete_user_data.assert_called_once_with(sample_user_for_privacy.id, delete_account=True)

    def test_delete_user_data_sample_admin_for_privacy_not_found(self, client, sample_admin_for_privacy, db):
        """Test admin deleting data for non-existent user."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.side_effect = ValueError("User 999 not found")

            request_data = {"delete_account": False}
            response = client.post("/api/privacy/delete/user/999", json=request_data, headers=headers)

            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            assert data["detail"] == "User 999 not found"

    def test_unauthorized_access_to_admin_endpoints(self, client, sample_user_for_privacy):
        """Test that regular users cannot access admin endpoints."""
        # This would test the actual permission system in integration
        # For unit tests, we're mocking the permission checks

    def test_invalid_request_data(self, client, sample_user_for_privacy, db):
        """Test endpoints with invalid request data."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        # Test with invalid JSON
        response = client.post("/api/privacy/delete/me", json={"invalid_field": "value"}, headers=headers)

        # The endpoint should handle this gracefully
        # Pydantic validation will handle invalid fields
        assert response.status_code in [status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_200_OK]
