from __future__ import annotations

from fastapi.testclient import TestClient
import pytest


@pytest.mark.integration
def test_admin_routes_require_admin(
    client: TestClient,
    auth_headers_student,
    auth_headers_instructor,
    auth_headers_admin,
) -> None:
    url = "/api/v1/admin/config/pricing"

    unauth = client.get(url)
    assert unauth.status_code in (401, 403)

    student = client.get(url, headers=auth_headers_student)
    assert student.status_code == 403

    instructor = client.get(url, headers=auth_headers_instructor)
    assert instructor.status_code == 403

    admin = client.get(url, headers=auth_headers_admin)
    assert admin.status_code == 200
