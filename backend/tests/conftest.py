# backend/tests/conftest.py
"""
Pytest configuration file.
This file is automatically loaded by pytest and sets up the test environment.
"""

import os
import sys

# Add the backend directory to Python path so imports work
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pytest
from sqlalchemy.orm import Session

# Now we can import from app
from app.database import Base, SessionLocal, engine


@pytest.fixture(scope="session")
def db():
    """Create a test database session."""
    # Create tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def test_db(db: Session):
    """Create a test database session with rollback."""
    # Start a transaction
    db.begin_nested()

    yield db

    # Rollback the transaction
    db.rollback()
