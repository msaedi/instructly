from datetime import datetime, timezone
import os

from scripts.seed_data import DEFAULT_ADMIN_PASSWORD, seed_admin_user
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth import verify_password
from app.core.enums import RoleName
from app.database import Base
from app.models.rbac import Role
from app.models.user import User


def _setup_session():
    previous_dialect = os.environ.get("DB_DIALECT")
    os.environ["DB_DIALECT"] = "sqlite"
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Role(name=RoleName.ADMIN.value, description="Admin role"))
        session.commit()
    if previous_dialect is not None:
        os.environ["DB_DIALECT"] = previous_dialect
    else:
        os.environ.pop("DB_DIALECT", None)
    return engine


def test_seed_admin_user_creates_and_updates():
    engine = _setup_session()
    with Session(engine) as session:
        seed_admin_user(
            session,
            email="admin@example.com",
            password_plain="Secret123!",
            name="Jane Admin",
            now=datetime.now(timezone.utc),
            verbose=False,
        )
    with Session(engine) as session:
        user = session.execute(select(User).where(User.email == "admin@example.com")).scalar_one()
        assert user.first_name == "Jane"
        assert verify_password("Secret123!", user.hashed_password)
        assert user.account_status == "active"
        assert user.roles[0].name == RoleName.ADMIN.value

    with Session(engine) as session:
        seed_admin_user(
            session,
            email="admin@example.com",
            password_plain="NewSecret123!",
            name="Jane Q Admin",
            now=datetime.now(timezone.utc),
            verbose=False,
        )
    with Session(engine) as session:
        user = session.execute(select(User).where(User.email == "admin@example.com")).scalar_one()
        assert user.last_name == "Q Admin"
        assert verify_password("NewSecret123!", user.hashed_password)
        assert len(user.roles) == 1


def test_seed_admin_user_requires_email():
    engine = _setup_session()
    with Session(engine) as session:
        try:
            seed_admin_user(
                session,
                email="",
                password_plain=DEFAULT_ADMIN_PASSWORD,
                name="Admin",
                now=datetime.now(timezone.utc),
                verbose=False,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for missing email")
