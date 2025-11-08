from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.repositories.instructor_profile_repository import InstructorProfileRepository


def ensure_allowed_durations_for_instructor(
    session: Session,
    *,
    instructor_user_id: str | None = None,
    instructor_profile_id: str | None = None,
    durations: Sequence[int] = (30, 60),
) -> None:
    """Ensure instructor services include the provided durations."""
    if not instructor_user_id and not instructor_profile_id:
        raise ValueError("Provide instructor_user_id or instructor_profile_id")

    repo = InstructorProfileRepository(session)
    if instructor_profile_id:
        profile = repo.get_by_id(instructor_profile_id)
    else:
        profile = repo.get_by_user_id(instructor_user_id)  # type: ignore[arg-type]

    if not profile:
        raise RuntimeError("Instructor profile not found")

    updated = False
    desired = set(durations)
    for service in getattr(profile, "instructor_services", []) or []:
        current = set(service.duration_options or [])
        target = sorted(current | desired)
        if target != (service.duration_options or []):
            service.duration_options = target
            updated = True

    if updated:
        session.flush()
