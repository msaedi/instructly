# backend/tests/test_minimal_booked_slots.py
"""
Minimal test to figure out the transaction issue
"""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, get_password_hash
from app.core.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole

# Create a simple test database connection
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_minimal_booked_slots():
    """Test without complex fixtures to isolate the issue."""

    # Create tables
    Base.metadata.create_all(bind=engine)

    # Create a fresh session
    db = SessionLocal()

    try:
        # Clean up any existing test data
        db.query(User).filter(User.email == "minimal.test@example.com").delete()
        db.commit()

        # Create a test instructor directly
        instructor = User(
            email="minimal.test@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Minimal Test Instructor",
            is_active=True,
            role=UserRole.INSTRUCTOR,
        )
        db.add(instructor)
        db.commit()

        # Create auth token
        token = create_access_token(data={"sub": instructor.email})
        headers = {"Authorization": f"Bearer {token}"}

        # Override get_db to use our session
        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        # Create test client
        with TestClient(app) as client:
            # Test the endpoint
            monday = date.today() - timedelta(days=date.today().weekday())
            response = client.get(
                "/instructors/availability-windows/week/booked-slots",
                params={"start_date": monday.isoformat()},
                headers=headers,
            )

            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")

            assert response.status_code == 200

    finally:
        # Cleanup
        app.dependency_overrides.clear()
        db.query(User).filter(User.email == "minimal.test@example.com").delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    test_minimal_booked_slots()
    print("Test passed!")
