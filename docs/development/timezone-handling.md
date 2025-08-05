# Timezone Handling Guide

## Overview

InstaInstru is a global platform that handles users across different timezones. This guide explains how to properly handle dates and times to ensure correct behavior for all users.

## Core Principles

### 1. All User-Facing Operations MUST Use User Timezone

Any operation that involves user data must consider the user's timezone:
- Availability management
- Booking validation
- Statistics calculations
- Date filtering
- "Today" calculations

### 2. System Operations Use System Time

Internal operations that don't affect users can use system time:
- Cache TTL management
- System logs
- Performance metrics
- Background job scheduling

### 3. Database Stores UTC

All timestamps in the database are stored in UTC for consistency.

## Available Functions

### Get User's "Today"

```python
from app.core.timezone_utils import get_user_today_by_id

# Get "today" in user's timezone
user_today = get_user_today_by_id(user_id, db)
```

### Get User's Current Time

```python
from app.core.timezone_utils import get_user_now

# Get current datetime in user's timezone
user_now = get_user_now(user)
```

### Get User's Timezone

```python
from app.core.timezone_utils import get_user_timezone

# Get pytz timezone object
user_tz = get_user_timezone(user)
```

## Common Patterns

### ✅ GOOD: Checking Past Dates

```python
def validate_availability(self, instructor_id: int, slot_date: date):
    instructor_today = get_user_today_by_id(instructor_id, self.db)
    if slot_date < instructor_today:
        raise ValidationError("Cannot add availability for past dates")
```

### ❌ BAD: Using System Date

```python
def validate_availability(self, instructor_id: int, slot_date: date):
    if slot_date < date.today():  # WRONG! Uses system timezone
        raise ValidationError("Cannot add availability for past dates")
```

### ✅ GOOD: Time Duration Calculations

```python
# Use a reference date for time math (timezone-agnostic)
reference_date = date(2024, 1, 1)
start_dt = datetime.combine(reference_date, start_time)
end_dt = datetime.combine(reference_date, end_time)
duration_minutes = (end_dt - start_dt).total_seconds() / 60
```

### ✅ GOOD: Monthly Statistics

```python
def get_monthly_stats(self, instructor_id: int):
    instructor_today = get_user_today_by_id(instructor_id, self.db)
    first_day_of_month = instructor_today.replace(day=1)
    # Calculate stats from first_day_of_month
```

## Service Layer Patterns

### Availability Service

```python
class AvailabilityService:
    def add_availability(self, instructor_id: int, slot_date: date):
        # Always use instructor's timezone
        instructor_today = get_user_today_by_id(instructor_id, self.db)

        if slot_date < instructor_today:
            raise ValidationError(
                f"Cannot add availability for {slot_date} "
                f"(today is {instructor_today} in your timezone)"
            )
```

### Booking Service

```python
class BookingService:
    def send_reminders(self):
        # Get system tomorrow as reference
        system_tomorrow = date.today() + timedelta(days=1)

        # Get all bookings for that date
        bookings = self.get_bookings_for_date(system_tomorrow)

        for booking in bookings:
            # Check if it's actually tomorrow for the instructor
            instructor_today = get_user_today_by_id(booking.instructor_id, self.db)
            instructor_tomorrow = instructor_today + timedelta(days=1)

            if booking.booking_date == instructor_tomorrow:
                # Send reminder
```

## Schema Layer Rules

### Date Validation Moved to Services

Schemas should NOT validate dates against "today" because they lack timezone context:

```python
# ❌ BAD: Schema validation
class AvailabilityCreate(BaseModel):
    slot_date: date

    @validator('slot_date')
    def validate_future(cls, v):
        if v < date.today():  # WRONG! No timezone context
            raise ValueError("Must be future date")
```

```python
# ✅ GOOD: Service validation
class AvailabilityService:
    def create_availability(self, user_id: int, data: AvailabilityCreate):
        user_today = get_user_today_by_id(user_id, self.db)
        if data.slot_date < user_today:
            raise ValidationError("Must be future date in your timezone")
```

## Testing Timezone Handling

### Test Different Timezones

```python
def test_cross_timezone_booking():
    # Instructor in Tokyo (UTC+9)
    instructor = Mock(timezone="Asia/Tokyo")

    # Student in New York (UTC-5)
    student = Mock(timezone="America/New_York")

    # Verify each sees correct "today"
    instructor_today = get_user_today_by_id(instructor.id, db)
    student_today = get_user_today_by_id(student.id, db)
```

### Test Edge Cases

See `tests/test_timezone_edge_cases.py` for comprehensive examples:
- Cross-timezone bookings
- DST transitions
- International date line
- CI environment (UTC)

## Common Mistakes to Avoid

### 1. Using date.today() in User Operations

```python
# ❌ WRONG
if booking_date < date.today():
    raise Error("Past date")

# ✅ CORRECT
user_today = get_user_today_by_id(user_id, db)
if booking_date < user_today:
    raise Error("Past date")
```

### 2. Forgetting Instructor Timezone in Availability

```python
# ❌ WRONG - Uses system timezone
available_slots = db.query(Slot).filter(
    Slot.date >= date.today()
)

# ✅ CORRECT - Uses instructor timezone
instructor_today = get_user_today_by_id(instructor_id, db)
available_slots = db.query(Slot).filter(
    Slot.date >= instructor_today
)
```

### 3. Mixing Timezone Contexts

```python
# ❌ WRONG - Comparing different timezone contexts
student_today = get_user_today_by_id(student_id, db)
if instructor_slot.date < student_today:  # WRONG!

# ✅ CORRECT - Use consistent context
instructor_today = get_user_today_by_id(instructor_id, db)
if instructor_slot.date < instructor_today:  # Correct
```

## Debugging Timezone Issues

### Check User Timezones

```python
# Log timezone info for debugging
logger.debug(f"User {user_id} timezone: {user.timezone}")
logger.debug(f"User's today: {get_user_today_by_id(user_id, db)}")
logger.debug(f"System today: {date.today()}")
```

### Common Symptoms of Timezone Bugs

1. **"It works for me but not for users in Asia"** - Using system timezone
2. **"Availability disappears at midnight"** - Wrong timezone for date boundary
3. **"Can't book for today"** - Instructor and student in different timezones
4. **"Stats are wrong"** - Using system date for calculations

## Pre-commit Hook

A pre-commit hook prevents `date.today()` in user-facing code:

```bash
# Install pre-commit hooks
pre-commit install

# The hook will catch this:
$ git commit
❌ Found date.today() usage in user-facing code!
File: app/services/booking_service.py
  Line 123: if booking_date < date.today():
    💡 Use: get_user_today_by_id(user_id, db) instead
```

## Quick Reference

| Operation | Wrong ❌ | Correct ✅ |
|-----------|----------|-----------|
| Check past date | `date < date.today()` | `date < get_user_today_by_id(user_id, db)` |
| Get current month | `date.today().replace(day=1)` | `get_user_today_by_id(user_id, db).replace(day=1)` |
| Filter future dates | `filter(date >= date.today())` | `filter(date >= get_user_today_by_id(user_id, db))` |
| Time duration | `datetime.combine(date.today(), time)` | `datetime.combine(reference_date, time)` |

## Summary

1. **Always** use user timezone for user-facing operations
2. **Never** use `date.today()` in routes, services, or API handlers
3. **Move** date validation from schemas to services
4. **Test** with multiple timezones
5. **Use** the pre-commit hook to prevent regressions

Remember: If it affects what a user sees or can do, it must use their timezone!
