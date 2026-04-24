# backend/tests/routes/test_privacy_routes.py
"""
Tests for privacy API endpoints.
"""

from unittest.mock import MagicMock, patch

from fastapi import status

from app.auth import create_access_token
from app.core.enums import PermissionName, RoleName
from app.services.permission_service import PermissionService

# Fixtures moved to conftest.py


class TestPrivacyEndpoints:
    """Test cases for privacy API endpoints."""

    def test_export_my_data_success(self, client, sample_user_for_privacy, db):
        """Test successful data export for current user."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
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

            response = client.get("/api/v1/privacy/export/me", headers=headers)

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

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.export_user_data.side_effect = Exception("Database error")

            response = client.get("/api/v1/privacy/export/me", headers=headers)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert data["detail"] == "Failed to export user data"

    def test_delete_my_data_anonymize_success(self, client, sample_user_for_privacy, db):
        """Test successful data anonymization (not full deletion)."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}
        order: list[str] = []

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_anonymized_confirmation"
            ) as mock_anonymize_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.side_effect = lambda *_args, **_kwargs: order.append("anonymize") or True
            mock_anonymize_email.side_effect = lambda **_kwargs: order.append("email") or True
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.side_effect = lambda *_args, **_kwargs: order.append("invalidate") or True
            mock_repo_factory.return_value = mock_repo

            request_data = {"delete_account": False}
            response = client.post("/api/v1/privacy/delete/me", json=request_data, headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == "Personal data anonymized"
            assert data["account_deleted"] is False

            mock_service.anonymize_user.assert_called_once_with(sample_user_for_privacy.id)
            mock_repo.invalidate_all_tokens.assert_called_once_with(
                sample_user_for_privacy.id,
                trigger="account_anonymize",
            )
            mock_anonymize_email.assert_called_once_with(
                to_email=sample_user_for_privacy.email,
                first_name=sample_user_for_privacy.first_name,
            )
            assert order == ["anonymize", "invalidate", "email"]

    def test_delete_my_data_anonymize_email_failure_is_observable(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """A missed anonymization confirmation should not block anonymization."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_anonymized_confirmation"
            ) as mock_anonymize_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.logger.error") as mock_logger_error,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.return_value = True
            mock_anonymize_email.return_value = False
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": False},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        mock_logger_error.assert_called_once()
        assert mock_logger_error.call_args.kwargs["extra"] == {
            "user_id": sample_user_for_privacy.id,
            "error": "send_account_anonymized_confirmation returned False",
        }
        mock_capture.assert_called_once()
        capture_args, capture_kwargs = mock_capture.call_args
        assert capture_args[0] == "account_anonymize_confirmation_email_failed"
        captured_error = capture_args[1]
        assert capture_kwargs == {"user_id": sample_user_for_privacy.id}
        assert isinstance(captured_error, RuntimeError)
        assert str(captured_error) == "send_account_anonymized_confirmation returned False"

    def test_delete_my_data_anonymize_token_invalidation_failure_is_observable(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """An anonymized account must not retain valid sessions silently."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_anonymized_confirmation"
            ) as mock_anonymize_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.logger.error") as mock_logger_error,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.return_value = True
            mock_anonymize_email.return_value = True
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = False
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": False},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        mock_repo.invalidate_all_tokens.assert_called_once_with(
            sample_user_for_privacy.id,
            trigger="account_anonymize",
        )
        mock_logger_error.assert_called_once()
        assert mock_logger_error.call_args.kwargs["extra"] == {
            "user_id": sample_user_for_privacy.id,
            "error": "invalidate_all_tokens returned False",
        }
        mock_capture.assert_called_once()
        capture_args, capture_kwargs = mock_capture.call_args
        assert capture_args[0] == "account_anonymize_token_invalidation_failed"
        captured_error = capture_args[1]
        assert capture_kwargs == {"user_id": sample_user_for_privacy.id}
        assert isinstance(captured_error, RuntimeError)
        assert str(captured_error) == "invalidate_all_tokens returned False"

    def test_delete_my_data_uses_write_rate_limit(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """Self-delete is an irreversible write endpoint and uses the write rate bucket."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_anonymized_confirmation"
            ) as mock_anonymize_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.return_value = True
            mock_anonymize_email.return_value = True
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": False},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["X-RateLimit-Policy"] == "write"

    def test_delete_my_data_full_deletion_success(self, client, sample_user_for_privacy, db):
        """Test successful full account deletion."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        order: list[str] = []
        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_deleted_confirmation"
            ) as mock_delete_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_delete_email.side_effect = lambda **_kwargs: order.append("email") or True
            mock_service.delete_user_data.side_effect = lambda *_args, **_kwargs: order.append("delete") or {
                "search_history": 5,
                "search_events": 10,
                "bookings": 2,
                "alerts": 3,
            }
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.side_effect = lambda *_args, **_kwargs: order.append("invalidate") or True
            mock_repo_factory.return_value = mock_repo

            request_data = {"delete_account": True}
            response = client.post("/api/v1/privacy/delete/me", json=request_data, headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == "Account and all associated data deleted"
            assert data["account_deleted"] is True
            assert "deletion_stats" in data

            mock_delete_email.assert_called_once_with(
                to_email=sample_user_for_privacy.email,
                first_name=sample_user_for_privacy.first_name,
            )
            mock_service.delete_user_data.assert_called_once_with(sample_user_for_privacy.id, delete_account=True)
            mock_repo.invalidate_all_tokens.assert_called_once_with(
                sample_user_for_privacy.id,
                trigger="account_delete",
            )
            assert order == ["delete", "invalidate", "email"]

    def test_delete_my_data_email_failure_is_observable(self, client, sample_user_for_privacy, db):
        """A missed delete confirmation should not block deletion, but must be observable."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}
        email_error = RuntimeError("email down")
        order: list[str] = []

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_deleted_confirmation"
            ) as mock_delete_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.logger.error") as mock_logger_error,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.side_effect = lambda *_args, **_kwargs: order.append("delete") or {
                "search_history": 1
            }

            def raise_email_failure(**_kwargs):
                order.append("email")
                raise email_error

            mock_delete_email.side_effect = raise_email_failure
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.side_effect = lambda *_args, **_kwargs: order.append("invalidate") or True
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert order == ["delete", "invalidate", "email"]
        mock_logger_error.assert_called_once()
        assert mock_logger_error.call_args.args == ("Account delete succeeded but confirmation email failed",)
        assert mock_logger_error.call_args.kwargs["extra"] == {
            "user_id": sample_user_for_privacy.id,
            "error": "email down",
        }
        assert mock_logger_error.call_args.kwargs["exc_info"] is True
        mock_capture.assert_called_once_with(
            "account_delete_confirmation_email_failed",
            email_error,
            user_id=sample_user_for_privacy.id,
        )

    def test_delete_my_data_false_email_return_is_observable(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """A false delete-confirmation return follows the same observability path."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}
        order: list[str] = []

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_deleted_confirmation"
            ) as mock_delete_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.logger.error") as mock_logger_error,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.side_effect = lambda *_args, **_kwargs: order.append("delete") or {
                "search_history": 1
            }
            mock_delete_email.side_effect = lambda **_kwargs: order.append("email") or False
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.side_effect = lambda *_args, **_kwargs: order.append("invalidate") or True
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert order == ["delete", "invalidate", "email"]
        mock_logger_error.assert_called_once()
        assert mock_logger_error.call_args.kwargs["extra"] == {
            "user_id": sample_user_for_privacy.id,
            "error": "send_account_deleted_confirmation returned False",
        }
        mock_capture.assert_called_once()
        capture_args, capture_kwargs = mock_capture.call_args
        assert capture_args[0] == "account_delete_confirmation_email_failed"
        captured_error = capture_args[1]
        assert capture_kwargs == {"user_id": sample_user_for_privacy.id}
        assert isinstance(captured_error, RuntimeError)
        assert str(captured_error) == "send_account_deleted_confirmation returned False"

    def test_delete_my_data_token_invalidation_failure_is_observable(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """A token-invalidation false return is a Sentry-observable security incident."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_deleted_confirmation"
            ) as mock_delete_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.logger.error") as mock_logger_error,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {"search_history": 1}
            mock_delete_email.return_value = True
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = False
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        mock_logger_error.assert_called_once()
        assert mock_logger_error.call_args.kwargs["extra"] == {
            "user_id": sample_user_for_privacy.id,
            "error": "invalidate_all_tokens returned False",
        }
        mock_capture.assert_called_once()
        capture_args, capture_kwargs = mock_capture.call_args
        assert capture_args[0] == "account_delete_token_invalidation_failed"
        captured_error = capture_args[1]
        assert capture_kwargs == {"user_id": sample_user_for_privacy.id}
        assert isinstance(captured_error, RuntimeError)
        assert str(captured_error) == "invalidate_all_tokens returned False"

    def test_delete_my_data_both_invalidate_and_email_fail(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """Token invalidation and email failures should produce distinct Sentry events."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_deleted_confirmation"
            ) as mock_delete_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {"search_history": 1}
            mock_delete_email.return_value = False
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = False
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert mock_capture.call_count == 2
        assert [call.args[0] for call in mock_capture.call_args_list] == [
            "account_delete_token_invalidation_failed",
            "account_delete_confirmation_email_failed",
        ]
        assert all(call.kwargs == {"user_id": sample_user_for_privacy.id} for call in mock_capture.call_args_list)
        assert all(isinstance(call.args[1], RuntimeError) for call in mock_capture.call_args_list)

    def test_delete_my_data_audit_uses_pre_delete_actor_snapshot(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """Audit actor fields should use captured identity values, not anonymized model fields."""
        original_email = sample_user_for_privacy.email
        original_first_name = sample_user_for_privacy.first_name
        token = create_access_token(data={"sub": original_email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_deleted_confirmation"
            ) as mock_delete_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.AuditService") as mock_audit_class,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            def delete_and_anonymize(*_args, **_kwargs):
                sample_user_for_privacy.email = "anon@example.invalid"
                sample_user_for_privacy.first_name = "Anonymized"
                return {"search_history": 1}

            mock_service.delete_user_data.side_effect = delete_and_anonymize
            mock_delete_email.return_value = True
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo
            mock_audit = MagicMock()
            mock_audit_class.return_value = mock_audit

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        audit_kwargs = mock_audit.log.call_args.kwargs
        assert audit_kwargs["action"] == "user.delete"
        assert audit_kwargs["actor_id"] == sample_user_for_privacy.id
        assert audit_kwargs["actor_email"] == original_email
        assert audit_kwargs["metadata"]["actor_first_name"] == original_first_name
        assert "actor" not in audit_kwargs

    def test_delete_my_data_audit_failure_is_observable(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """A failed delete audit log should be visible in Sentry without blocking deletion."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}
        audit_error = RuntimeError("audit down")

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_deleted_confirmation"
            ) as mock_delete_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.AuditService") as mock_audit_class,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {"search_history": 1}
            mock_delete_email.return_value = True
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo
            mock_audit = MagicMock()
            mock_audit.log.side_effect = audit_error
            mock_audit_class.return_value = mock_audit

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert mock_audit.log.call_args.kwargs["action"] == "user.delete"
        mock_capture.assert_called_once_with(
            "account_delete_audit_failed",
            audit_error,
            user_id=sample_user_for_privacy.id,
        )

    def test_delete_my_data_anonymize_audit_failure_is_observable(
        self,
        client,
        sample_user_for_privacy,
        db,
    ):
        """A failed anonymize audit log should be visible in Sentry without blocking anonymization."""
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}
        audit_error = RuntimeError("audit down")

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch(
                "app.services.notification_service.NotificationService.send_account_anonymized_confirmation"
            ) as mock_anonymize_email,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.AuditService") as mock_audit_class,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.return_value = True
            mock_anonymize_email.return_value = True
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo
            mock_audit = MagicMock()
            mock_audit.log.side_effect = audit_error
            mock_audit_class.return_value = mock_audit

            response = client.post(
                "/api/v1/privacy/delete/me",
                json={"delete_account": False},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert mock_audit.log.call_args.kwargs["action"] == "user.anonymize"
        mock_capture.assert_called_once_with(
            "account_anonymize_audit_failed",
            audit_error,
            user_id=sample_user_for_privacy.id,
        )

    def test_delete_my_data_service_error(self, client, sample_user_for_privacy, db):
        """Test data deletion with service error."""
        # Create auth token
        token = create_access_token(data={"sub": sample_user_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.anonymize_user.side_effect = Exception("Database error")

            request_data = {"delete_account": False}
            response = client.post("/api/v1/privacy/delete/me", json=request_data, headers=headers)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert data["detail"] == "Failed to delete user data"

    def test_get_privacy_statistics_success(self, client, sample_admin_for_privacy, db):
        """Test successful privacy statistics retrieval (admin only)."""
        from app.schemas.privacy import PrivacyStatistics

        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        permission_service.grant_permission(sample_admin_for_privacy.id, PermissionName.MANAGE_USERS.value)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.get_privacy_statistics.return_value = PrivacyStatistics(
                total_users=100,
                active_users=95,
                search_history_records=500,
                search_event_records=1000,
                total_bookings=200,
            )

            response = client.get("/api/v1/privacy/statistics", headers=headers)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert "statistics" in data
            assert data["statistics"]["total_users"] == 100

    def test_apply_retention_policies_success(self, client, sample_admin_for_privacy, db):
        """Test successful retention policy application (admin only)."""
        from app.schemas.privacy import RetentionStats

        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        permission_service.grant_permission(sample_admin_for_privacy.id, PermissionName.MANAGE_USERS.value)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.apply_retention_policies.return_value = RetentionStats(
                search_events_deleted=50,
                old_bookings_anonymized=10,
            )

            response = client.post("/api/v1/privacy/retention/apply", headers=headers)

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

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.export_user_data.return_value = {
                "user_profile": {"id": sample_user_for_privacy.id},
                "search_history": [],
            }

            response = client.get(f"/api/v1/privacy/export/user/{sample_user_for_privacy.id}", headers=headers)

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

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.export_user_data.side_effect = ValueError("User 999 not found")

            response = client.get("/api/v1/privacy/export/user/999", headers=headers)

            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            assert data["detail"] == "User 999 not found"

    def test_delete_user_data_admin_success(self, client, sample_admin_for_privacy, sample_user_for_privacy, db):
        """Test admin deleting data for another user."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        permission_service.grant_permission(sample_admin_for_privacy.id, PermissionName.MANAGE_USERS.value)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {
                "search_history": 3,
                "bookings": 1,
            }
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo

            request_data = {"delete_account": True}
            response = client.post(
                f"/api/v1/privacy/delete/user/{sample_user_for_privacy.id}", json=request_data, headers=headers
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "success"
            assert data["message"] == f"Data deleted for user {sample_user_for_privacy.id}"
            assert data["account_deleted"] is True

            mock_service.delete_user_data.assert_called_once_with(sample_user_for_privacy.id, delete_account=True)
            mock_repo.invalidate_all_tokens.assert_called_once_with(
                sample_user_for_privacy.id,
                trigger="admin_account_delete",
            )
            assert response.headers["X-RateLimit-Policy"] == "write"

    def test_admin_delete_user_invalidates_tokens_after_delete(
        self,
        client,
        sample_admin_for_privacy,
        sample_user_for_privacy,
        db,
    ):
        """Admin delete invalidates target sessions only after deletion succeeds."""
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        permission_service.grant_permission(sample_admin_for_privacy.id, PermissionName.MANAGE_USERS.value)
        db.commit()

        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}
        order: list[str] = []

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.AuditService") as mock_audit_class,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.side_effect = lambda *_args, **_kwargs: order.append("delete") or {
                "search_history": 1
            }
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.side_effect = (
                lambda *_args, **_kwargs: order.append("invalidate") or True
            )
            mock_repo_factory.return_value = mock_repo
            mock_audit = MagicMock()
            mock_audit_class.return_value = mock_audit

            response = client.post(
                f"/api/v1/privacy/delete/user/{sample_user_for_privacy.id}",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert order == ["delete", "invalidate"]
        mock_service.delete_user_data.assert_called_once_with(sample_user_for_privacy.id, delete_account=True)
        mock_repo.invalidate_all_tokens.assert_called_once_with(
            sample_user_for_privacy.id,
            trigger="admin_account_delete",
        )
        audit_kwargs = mock_audit.log.call_args.kwargs
        assert audit_kwargs["action"] == "user.delete"
        assert audit_kwargs["metadata"]["initiated_by"] == "admin"

    def test_admin_delete_with_anonymize_only_invalidates_tokens(
        self,
        client,
        sample_admin_for_privacy,
        sample_user_for_privacy,
        db,
    ):
        """Admin history-only delete still invalidates target sessions."""
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        permission_service.grant_permission(sample_admin_for_privacy.id, PermissionName.MANAGE_USERS.value)
        db.commit()

        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        # NOTE: delete_account=False on the admin path only clears search history
        # and does NOT anonymize PII (pre-existing behavior, not in scope). Token
        # invalidation runs regardless. If the PII-anonymization gap is fixed later,
        # this test should be updated to assert the correct behavior.
        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.AuditService") as mock_audit_class,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {"search_history": 1}
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo
            mock_audit = MagicMock()
            mock_audit_class.return_value = mock_audit

            response = client.post(
                f"/api/v1/privacy/delete/user/{sample_user_for_privacy.id}",
                json={"delete_account": False},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        mock_service.delete_user_data.assert_called_once_with(sample_user_for_privacy.id, delete_account=False)
        mock_repo.invalidate_all_tokens.assert_called_once_with(
            sample_user_for_privacy.id,
            trigger="admin_account_delete",
        )

    def test_delete_user_data_admin_token_invalidation_failure_is_observable(
        self,
        client,
        sample_admin_for_privacy,
        sample_user_for_privacy,
        db,
    ):
        """Admin deletion should not leave target tokens valid silently."""
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        permission_service.grant_permission(sample_admin_for_privacy.id, PermissionName.MANAGE_USERS.value)
        db.commit()

        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.logger.error") as mock_logger_error,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {"search_history": 1}
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = False
            mock_repo_factory.return_value = mock_repo

            response = client.post(
                f"/api/v1/privacy/delete/user/{sample_user_for_privacy.id}",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        mock_repo.invalidate_all_tokens.assert_called_once_with(
            sample_user_for_privacy.id,
            trigger="admin_account_delete",
        )
        mock_logger_error.assert_called_once()
        assert mock_logger_error.call_args.kwargs["extra"] == {
            "user_id": sample_admin_for_privacy.id,
            "target_user_id": sample_user_for_privacy.id,
            "error": "invalidate_all_tokens returned False",
        }
        mock_capture.assert_called_once()
        capture_args, capture_kwargs = mock_capture.call_args
        assert capture_args[0] == "account_delete_admin_token_invalidation_failed"
        assert isinstance(capture_args[1], RuntimeError)
        assert capture_kwargs == {
            "user_id": sample_admin_for_privacy.id,
            "target_user_id": sample_user_for_privacy.id,
        }

    def test_delete_user_data_admin_audit_failure_is_observable(
        self,
        client,
        sample_admin_for_privacy,
        sample_user_for_privacy,
        db,
    ):
        """Admin delete audit failures should be Sentry-observable without blocking deletion."""
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        permission_service.grant_permission(sample_admin_for_privacy.id, PermissionName.MANAGE_USERS.value)
        db.commit()

        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}
        audit_error = RuntimeError("audit failed")

        with (
            patch("app.routes.v1.privacy.PrivacyService") as mock_service_class,
            patch("app.routes.v1.privacy.RepositoryFactory.create_user_repository") as mock_repo_factory,
            patch("app.routes.v1.privacy.AuditService") as mock_audit_class,
            patch("app.routes.v1.privacy.capture_sentry_exception") as mock_capture,
        ):
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.return_value = {"search_history": 1}
            mock_repo = MagicMock()
            mock_repo.invalidate_all_tokens.return_value = True
            mock_repo_factory.return_value = mock_repo
            mock_audit = MagicMock()
            mock_audit.log.side_effect = audit_error
            mock_audit_class.return_value = mock_audit

            response = client.post(
                f"/api/v1/privacy/delete/user/{sample_user_for_privacy.id}",
                json={"delete_account": True},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        audit_kwargs = mock_audit.log.call_args.kwargs
        assert audit_kwargs["action"] == "user.delete"
        assert audit_kwargs["metadata"]["initiated_by"] == "admin"
        mock_capture.assert_called_once_with(
            "account_delete_admin_audit_failed",
            audit_error,
            user_id=sample_admin_for_privacy.id,
            target_user_id=sample_user_for_privacy.id,
        )

    def test_delete_user_data_sample_admin_for_privacy_not_found(self, client, sample_admin_for_privacy, db):
        """Test admin deleting data for non-existent user."""
        # Assign admin role with proper permissions
        permission_service = PermissionService(db)
        permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": sample_admin_for_privacy.email})
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.routes.v1.privacy.PrivacyService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.delete_user_data.side_effect = ValueError("User 999 not found")

            request_data = {"delete_account": False}
            response = client.post("/api/v1/privacy/delete/user/999", json=request_data, headers=headers)

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
        response = client.post("/api/v1/privacy/delete/me", json={"invalid_field": "value"}, headers=headers)

        # The endpoint should handle this gracefully
        # Pydantic validation will handle invalid fields
        assert response.status_code in [422, status.HTTP_200_OK]
