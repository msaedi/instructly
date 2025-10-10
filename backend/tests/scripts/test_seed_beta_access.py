from scripts.seed_data import seed_beta_access_for_instructors
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.database import Base
from app.models.beta import BetaAccess, BetaSettings
from app.models.rbac import Role
from app.models.user import User


def _build_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _mk_user(email: str) -> User:
    return User(
        email=email,
        hashed_password="hashed",
        first_name="Test",
        last_name="User",
        zip_code="10001",
    )


def test_seed_beta_access_grants_and_is_idempotent():
    engine = _build_engine()

    with Session(engine) as session:
        instructor_role = Role(name=RoleName.INSTRUCTOR.value, description="Instructor")
        student_role = Role(name=RoleName.STUDENT.value, description="Student")
        session.add_all([instructor_role, student_role])
        session.flush()

        instructor_one = _mk_user("inst1@example.com")
        instructor_one.roles.append(instructor_role)
        instructor_two = _mk_user("inst2@example.com")
        instructor_two.roles.append(instructor_role)
        student_user = _mk_user("student@example.com")
        student_user.roles.append(student_role)

        session.add_all([instructor_one, instructor_two, student_user])
        session.commit()

        created, existing = seed_beta_access_for_instructors(session)
        assert created == 2
        assert existing == 0

        grants = session.execute(select(BetaAccess)).scalars().all()
        assert len(grants) == 2
        assert all(grant.role == "instructor" for grant in grants)
        assert all(grant.phase == "instructor_only" for grant in grants)
        # Ensure beta settings row exists (singleton semantics)
        assert session.execute(select(BetaSettings)).scalar_one()

    with Session(engine) as session:
        created, existing = seed_beta_access_for_instructors(session)
        assert created == 0
        assert existing == 2

        grants = session.execute(select(BetaAccess)).scalars().all()
        assert len(grants) == 2
