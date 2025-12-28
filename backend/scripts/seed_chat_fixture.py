"""Seed helper that ensures a demo chat booking exists."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
import os
from typing import Callable, Iterable, Optional

import pytz
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal

try:  # pragma: no cover - helper only available in repo environments
    from backend.tests._utils.service_seed import ensure_instructor_service_for_tests
except ModuleNotFoundError:  # pragma: no cover
    ensure_instructor_service_for_tests = None  # type: ignore[assignment]

try:  # pragma: no cover - repository may not be importable in all environments
    from app.repositories.conversation_repository import ConversationRepository
except ModuleNotFoundError:  # pragma: no cover
    ConversationRepository = None  # type: ignore[assignment,misc]


CHAT_TIMEZONE = pytz.timezone("America/New_York")


def _bool_env(raw: Optional[str], default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _localize(day: date, value: time) -> datetime:
    naive = datetime.combine(day, value)  # tz-pattern-ok: seed script generates test data
    return CHAT_TIMEZONE.localize(naive)


def _format_slot(day: date, start: time) -> str:
    return _localize(day, start).isoformat()


def _existing_fixture(
    session: Session, *, instructor_id: str, student_id: str, now: datetime, horizon_days: int = 14
) -> Optional:
    """Check if a fixture booking already exists."""
    # Lazy import to avoid import-time failures
    from app.models.booking import Booking, BookingStatus

    horizon = now + timedelta(days=horizon_days)
    return (
        session.query(Booking)
        .filter(
            Booking.instructor_id == instructor_id,
            Booking.student_id == student_id,
            Booking.status.in_((BookingStatus.CONFIRMED.value, BookingStatus.PENDING.value)),
            Booking.booking_date >= now.date(),
            Booking.booking_date <= horizon.date(),
        )
        .order_by(Booking.booking_date.asc(), Booking.start_time.asc())
        .first()
    )


def _get_user_by_email(session: Session, email: str):
    from app.models.user import User

    return session.query(User).filter(User.email == email).one_or_none()


def _ensure_profile(session: Session, instructor) -> object:
    """Ensure instructor profile exists."""
    # Lazy import to avoid import-time failures
    from app.models.instructor import InstructorProfile

    profile = (
        session.query(InstructorProfile).filter(InstructorProfile.user_id == instructor.id).one_or_none()
    )
    if profile:
        return profile

    profile = InstructorProfile(
        user_id=instructor.id,
        bio="Auto-generated chat fixture profile",
        years_experience=5,
        min_advance_booking_hours=24,
        buffer_time_minutes=0,
        skills_configured=True,
        is_live=True,
    )
    session.add(profile)
    session.flush()
    return profile


def _ensure_service(
    session: Session,
    *,
    profile: object,
    duration_minutes: int,
    service_name: str,
) -> object:
    """Ensure instructor service exists."""
    # Lazy import to avoid import-time failures
    from app.models.service_catalog import InstructorService

    service: Optional[InstructorService] = (
        session.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == profile.id)
        .order_by(InstructorService.created_at.desc())
        .first()
    )
    if service and duration_minutes in service.duration_options:
        return service

    if ensure_instructor_service_for_tests is None:
        if service is None:
            raise RuntimeError("ensure_instructor_service_for_tests helper unavailable")
        options = set(service.duration_options or [])
        options.add(duration_minutes)
        service.duration_options = sorted(options)
        session.flush()
        return service

    _, service_id = ensure_instructor_service_for_tests(  # type: ignore[misc]
        session,
        instructor_profile_id=profile.id,
        service_name=service_name,
        duration_minutes=duration_minutes,
        hourly_rate=float(service.hourly_rate if service else 80.0),
        is_active=True,
    )
    service = session.get(InstructorService, service_id)
    assert service is not None  # safety
    return service


def _ensure_bitmap_window(
    session: Session,
    *,
    instructor_id: str,
    target_day: date,
    start: time,
    end: time,
) -> None:
    """Ensure bitmap availability window exists for the target day."""
    # Lazy import to avoid import-time failures
    from app.services.availability_service import AvailabilityService

    svc = AvailabilityService(db=session)

    # Calculate week_start (Monday of the week containing target_day)
    week_start = target_day - timedelta(days=target_day.weekday())

    # Build windows_by_day dict: {date: [("HH:MM:SS", "HH:MM:SS"), ...]}
    windows_by_day = {}
    start_str = start.strftime("%H:%M:%S")
    end_str = end.strftime("%H:%M:%S")

    # Add the target window
    windows_by_day[target_day] = [(start_str, end_str)]

    # Use save_week_bits with clear_existing=False to merge with existing
    svc.save_week_bits(
        instructor_id=instructor_id,
        week_start=week_start,
        windows_by_day=windows_by_day,
        base_version=None,
        override=False,
        clear_existing=False,
    )


def _has_booking_conflict(
    session: Session,
    *,
    instructor_id: str,
    target_day: date,
    start_time: time,
    end_time: time,
) -> bool:
    from app.models.booking import Booking, BookingStatus

    conflict = (
        session.query(Booking)
        .filter(
            Booking.instructor_id == instructor_id,
            Booking.booking_date == target_day,
            Booking.start_time < end_time,
            Booking.end_time > start_time,
            Booking.status.in_((BookingStatus.CONFIRMED.value, BookingStatus.PENDING.value)),
        )
        .first()
    )
    return conflict is not None


def _candidate_times(day: date, *, base_hour: int, duration_minutes: int) -> Iterable[tuple[time, time, datetime]]:
    base_start = datetime.combine(  # tz-pattern-ok: seed script generates test data
        day, time(hour=base_hour, minute=0)
    )
    for offset in range(4):
        candidate_start = base_start + timedelta(minutes=offset * 30)
        if candidate_start.date() != day:
            continue
        candidate_end = candidate_start + timedelta(minutes=duration_minutes)
        if candidate_end.date() != day:
            continue
        yield candidate_start.time(), candidate_end.time(), candidate_start


def _ensure_conversation(session: Session, *, student_id: str, instructor_id: str) -> Optional[object]:
    """Ensure a conversation exists between student and instructor.

    Returns the conversation if created/found, None if ConversationRepository unavailable.
    """
    if ConversationRepository is None:
        return None

    try:
        repo = ConversationRepository(db=session)
        conversation, created = repo.get_or_create(
            student_id=student_id,
            instructor_id=instructor_id,
        )
        if created:
            print(f"  created conversation for student={student_id} instructor={instructor_id}")
        return conversation
    except Exception as exc:
        print(f"  warning: conversation creation failed: {exc}")
        return None


def seed_chat_fixture_booking(
    *,
    instructor_email: str,
    student_email: str,
    start_hour: int,
    duration_minutes: int,
    days_ahead_min: int,
    days_ahead_max: int,
    location: str,
    service_name: str,
    session_factory: Callable[[], Session] = SessionLocal,
) -> str:
    """Create a minimal chat/booking fixture using bitmap availability."""
    default_enabled = settings.site_mode.lower() not in {"prod", "production", "beta", "live"}
    seed_enabled = _bool_env(os.getenv("SEED_CHAT_FIXTURE"), default_enabled)
    if not seed_enabled:
        return "disabled"

    from app.services.cache_service import CacheService
    from app.services.search.cache_invalidation import init_search_cache

    init_search_cache(CacheService())

    try:
        from app.models.booking import Booking, BookingStatus
    except Exception as e:
        print(f"chat fixture skipped: imports unavailable: {e}")
        return "imports-missing"

    session = session_factory()
    try:
        now = datetime.now(CHAT_TIMEZONE)
        instructor = _get_user_by_email(session, instructor_email)
        student = _get_user_by_email(session, student_email)
        if not instructor or not student:
            print(
                f"chat fixture skipped: missing users "
                f"(instructor={'present' if instructor else 'absent'}, "
                f"student={'present' if student else 'absent'})"
            )
            return "missing-users"

        profile = _ensure_profile(session, instructor)
        service = _ensure_service(
            session,
            profile=profile,
            duration_minutes=duration_minutes,
            service_name=service_name,
        )
        session.commit()

        allowed_durations = sorted({int(d) for d in (service.duration_options or []) if d})
        if not allowed_durations:
            allowed_durations = [duration_minutes or 60]
            service.duration_options = allowed_durations
            session.commit()
        elif set(allowed_durations) != set(service.duration_options or []):
            service.duration_options = allowed_durations
            session.commit()

        if duration_minutes in allowed_durations:
            slot_duration = duration_minutes
        elif 60 in allowed_durations:
            slot_duration = 60
        else:
            slot_duration = allowed_durations[0]

        existing = _existing_fixture(session, instructor_id=instructor.id, student_id=student.id, now=now)
        if existing:
            start_dt = _localize(existing.booking_date, existing.start_time)
            if start_dt > now:
                print(
                    f"chat fixture booking skipped: already exists at {start_dt.isoformat()} "
                    f"({existing.status}) instructor={instructor.id} student={student.id}"
                )
                return "skipped-existing"

        min_day = (now + timedelta(days=days_ahead_min)).date()
        max_day = (now + timedelta(days=days_ahead_max)).date()
        if max_day < min_day:
            min_day, max_day = max_day, min_day

        min_advance_hours = profile.min_advance_booking_hours or 24
        min_start = now + timedelta(hours=min_advance_hours)

        for delta in range((max_day - min_day).days + 1):
            candidate_day = min_day + timedelta(days=delta)
            for start_time, end_time, naive_start in _candidate_times(
                candidate_day, base_hour=start_hour, duration_minutes=slot_duration
            ):
                localized_start = CHAT_TIMEZONE.localize(naive_start)
                if localized_start <= min_start:
                    continue

                if _has_booking_conflict(
                    session,
                    instructor_id=instructor.id,
                    target_day=candidate_day,
                    start_time=start_time,
                    end_time=end_time,
                ):
                    continue

                try:
                    _ensure_bitmap_window(
                        session,
                        instructor_id=instructor.id,
                        target_day=candidate_day,
                        start=start_time,
                        end=end_time,
                    )

                    hourly_rate = Decimal(str(service.hourly_rate or 80)).quantize(Decimal("0.01"))
                    total_price = (
                        hourly_rate * Decimal(slot_duration) / Decimal(60)
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                    booking = Booking(
                        student_id=student.id,
                        instructor_id=instructor.id,
                        instructor_service_id=service.id,
                        booking_date=candidate_day,
                        start_time=start_time,
                        end_time=end_time,
                        status=BookingStatus.CONFIRMED.value,
                        service_name=service_name or service.name,
                        hourly_rate=hourly_rate,
                        total_price=total_price,
                        duration_minutes=slot_duration,
                        location_type=location,
                        meeting_location=location,
                    )
                    session.add(booking)
                    session.commit()

                    # Create conversation for this student-instructor pair
                    _ensure_conversation(
                        session,
                        student_id=student.id,
                        instructor_id=instructor.id,
                    )
                    session.commit()

                    print(
                        f"created chat fixture booking: {localized_start.isoformat()} "
                        f"(CONFIRMED) instructor={instructor.id} student={student.id}"
                    )
                    return "created"
                except IntegrityError:
                    session.rollback()
                    continue

        print(
            "chat fixture booking skipped: no available slot found within window "
            f"{min_day.isoformat()}–{max_day.isoformat()}"
        )
        return "no-slot"
    except Exception as exc:  # pragma: no cover - defensive logging
        session.rollback()
        print(f"chat fixture booking failed: {exc}")
        return "error"
    finally:
        session.close()
