"""
Integration tests for the generate-bio endpoint.
Mocks OpenAI at the service level to avoid real API calls.
"""

from unittest.mock import AsyncMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from app.models.user import User


class TestGenerateBioEndpoint:
    """Tests for POST /api/v1/instructors/me/generate-bio."""

    def test_requires_auth(self, client: TestClient):
        """Unauthenticated request returns 401."""
        response = client.post("/api/v1/instructors/me/generate-bio")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_gets_404(
        self,
        client: TestClient,
        test_student: User,
        auth_headers_student: dict,
    ):
        """Student without instructor profile gets 404."""
        with patch(
            "app.routes.v1.instructors.BioGenerationService.generate_bio",
            new_callable=AsyncMock,
        ) as mock_gen:
            from app.core.exceptions import NotFoundException

            mock_gen.side_effect = NotFoundException("Instructor profile not found")
            response = client.post(
                "/api/v1/instructors/me/generate-bio",
                headers=auth_headers_student,
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_success(
        self,
        client: TestClient,
        test_instructor: User,
        auth_headers_instructor: dict,
    ):
        """Authenticated instructor gets a generated bio."""
        with patch(
            "app.routes.v1.instructors.BioGenerationService.generate_bio",
            new_callable=AsyncMock,
            return_value="I am a passionate piano teacher with 5 years of experience.",
        ):
            response = client.post(
                "/api/v1/instructors/me/generate-bio",
                headers=auth_headers_instructor,
            )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "bio" in data
        assert isinstance(data["bio"], str)
        assert len(data["bio"]) > 0

    def test_service_unavailable(
        self,
        client: TestClient,
        test_instructor: User,
        auth_headers_instructor: dict,
    ):
        """Service exception returns 503."""
        with patch(
            "app.routes.v1.instructors.BioGenerationService.generate_bio",
            new_callable=AsyncMock,
        ) as mock_gen:
            from app.core.exceptions import ServiceException

            mock_gen.side_effect = ServiceException("Bio generation temporarily unavailable")
            response = client.post(
                "/api/v1/instructors/me/generate-bio",
                headers=auth_headers_instructor,
            )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
