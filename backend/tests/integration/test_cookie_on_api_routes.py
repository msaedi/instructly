from fastapi.testclient import TestClient

from app.auth import create_access_token, get_password_hash
from app.core.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.user import User


def _ensure_user(email: str) -> None:
    session = SessionLocal()
    try:
        existing = session.query(User).filter(User.email == email).first()
        if existing:
            return
        user = User(
            email=email,
            hashed_password=get_password_hash("Test1234!"),
            first_name="Cookie",
            last_name="Tester",
            zip_code="10001",
            is_active=True,
        )
        session.add(user)
        session.commit()
    finally:
        session.close()


def test_session_cookie_auth_on_api_addresses():
    email = "cookie-test@example.com"
    _ensure_user(email)
    client = TestClient(app)
    token = create_access_token({"sub": email})
    client.cookies.set(settings.session_cookie_name, token)

    response = client.get("/api/v1/addresses/me")

    assert response.status_code == 200
