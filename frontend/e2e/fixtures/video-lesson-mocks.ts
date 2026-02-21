/**
 * Mock data factories and pre-built fixtures for video lesson E2E tests.
 *
 * All datetime values use offsets from Date.now() to avoid cross-midnight flakiness.
 * The minutesFromNow() helper is the single source of truth for relative timestamps.
 */
import { addDays, format } from 'date-fns';
import { TEST_ULIDS } from './ulids';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** ISO timestamp offset from now. Positive = future, negative = past. */
export function minutesFromNow(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toISOString();
}

const FUTURE_DATE = addDays(new Date(), 7);
const futureISO = format(FUTURE_DATE, 'yyyy-MM-dd');

// ---------------------------------------------------------------------------
// User fixtures
// ---------------------------------------------------------------------------

export const STUDENT_USER = {
  id: TEST_ULIDS.studentUser1,
  email: 'video-student@example.com',
  first_name: 'Alex',
  last_name: 'Student',
  roles: ['student'],
  permissions: [],
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

export const INSTRUCTOR_USER = {
  id: TEST_ULIDS.instructor8,
  email: 'video-instructor@example.com',
  first_name: 'Sarah',
  last_name: 'Chen',
  roles: ['instructor'],
  permissions: [],
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

// ---------------------------------------------------------------------------
// Booking factory
// ---------------------------------------------------------------------------

type BookingOverrides = Record<string, unknown>;

export function makeVideoBooking(overrides: BookingOverrides = {}) {
  const defaults = {
    id: TEST_ULIDS.videoBooking1,
    student_id: TEST_ULIDS.studentUser1,
    instructor_id: TEST_ULIDS.instructor8,
    instructor_service_id: TEST_ULIDS.service1,
    booking_date: futureISO,
    start_time: '14:00:00',
    end_time: '15:00:00',
    scheduled_start: minutesFromNow(10),
    scheduled_end: minutesFromNow(70),
    status: 'CONFIRMED',
    service_name: 'Piano Lesson',
    hourly_rate: 60,
    total_price: 60,
    duration_minutes: 60,
    location_type: 'online',
    location_details: 'Online Video Lesson',
    meeting_location: 'Online Video Lesson',
    instructor: {
      id: TEST_ULIDS.instructor8,
      first_name: 'Sarah',
      last_initial: 'C',
    },
    student: {
      id: TEST_ULIDS.studentUser1,
      first_name: 'Alex',
      last_name: 'Student',
      email: 'video-student@example.com',
    },
    // Video fields
    video_room_id: 'room_test_e2e_001',
    video_session_started_at: null,
    video_session_ended_at: null,
    video_session_duration_seconds: null,
    video_instructor_joined_at: null,
    video_student_joined_at: null,
    // Join window
    can_join_lesson: true,
    join_opens_at: minutesFromNow(-60),
    join_closes_at: minutesFromNow(60),
  };

  return { ...defaults, ...overrides };
}

// ---------------------------------------------------------------------------
// Pre-built booking fixtures
// ---------------------------------------------------------------------------

/** Online CONFIRMED booking with join window currently open (±60 min). */
export function bookingJoinable(overrides: BookingOverrides = {}) {
  return makeVideoBooking({
    id: TEST_ULIDS.videoBooking1,
    join_opens_at: minutesFromNow(-60),
    join_closes_at: minutesFromNow(60),
    ...overrides,
  });
}

/** Online CONFIRMED booking where join window opens in 120 minutes. */
export function bookingNotYetJoinable(overrides: BookingOverrides = {}) {
  return makeVideoBooking({
    id: TEST_ULIDS.videoBooking2,
    join_opens_at: minutesFromNow(120),
    join_closes_at: minutesFromNow(180),
    can_join_lesson: false,
    ...overrides,
  });
}

/** Online CONFIRMED booking where join window has closed. */
export function bookingWindowClosed(overrides: BookingOverrides = {}) {
  return makeVideoBooking({
    id: TEST_ULIDS.videoBooking2,
    join_opens_at: minutesFromNow(-120),
    join_closes_at: minutesFromNow(-60),
    can_join_lesson: false,
    ...overrides,
  });
}

/** Completed booking with video session stats. Duration: 2712s = 45m 12s. */
export function bookingEndedWithStats(overrides: BookingOverrides = {}) {
  return makeVideoBooking({
    id: TEST_ULIDS.videoBooking3,
    status: 'COMPLETED',
    video_session_started_at: '2026-02-21T14:00:00Z',
    video_session_ended_at: '2026-02-21T14:45:12Z',
    video_session_duration_seconds: 2712,
    video_instructor_joined_at: '2026-02-21T13:58:30Z',
    video_student_joined_at: '2026-02-21T14:00:15Z',
    join_opens_at: null,
    join_closes_at: null,
    can_join_lesson: false,
    ...overrides,
  });
}

/** Completed booking with ended_at but all video stats null. */
export function bookingEndedNoStats(overrides: BookingOverrides = {}) {
  return makeVideoBooking({
    id: TEST_ULIDS.videoBooking4,
    status: 'COMPLETED',
    video_session_ended_at: '2026-02-21T14:45:00Z',
    video_session_duration_seconds: null,
    video_instructor_joined_at: null,
    video_student_joined_at: null,
    join_opens_at: null,
    join_closes_at: null,
    can_join_lesson: false,
    ...overrides,
  });
}

/** Cancelled online booking. */
export function bookingCancelled(overrides: BookingOverrides = {}) {
  return makeVideoBooking({
    id: TEST_ULIDS.videoBooking5,
    status: 'CANCELLED',
    join_opens_at: null,
    join_closes_at: null,
    can_join_lesson: false,
    ...overrides,
  });
}

/** In-person booking (no video). */
export function bookingInPerson(overrides: BookingOverrides = {}) {
  return makeVideoBooking({
    id: TEST_ULIDS.videoBooking6,
    location_type: 'student_location',
    location_details: 'Upper East Side, NYC',
    meeting_location: 'Upper East Side, NYC',
    video_room_id: null,
    join_opens_at: null,
    join_closes_at: null,
    can_join_lesson: false,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// API response fixtures
// ---------------------------------------------------------------------------

/** Video session status for a completed lesson. */
export const VIDEO_SESSION_DATA = {
  room_id: 'room_test_e2e_001',
  session_started_at: '2026-02-21T14:00:00Z',
  session_ended_at: '2026-02-21T14:45:12Z',
  instructor_joined_at: '2026-02-21T13:58:30Z',
  student_joined_at: '2026-02-21T14:00:15Z',
};

/** Empty video session (no data yet). */
export const VIDEO_SESSION_EMPTY = {
  room_id: 'room_test_e2e_001',
  session_started_at: null,
  session_ended_at: null,
  instructor_joined_at: null,
  student_joined_at: null,
};

/** Successful join response. */
export const VIDEO_JOIN_RESPONSE = {
  auth_token: 'mock_hms_auth_token_e2e',
  room_id: 'room_test_e2e_001',
  role: 'guest',
  booking_id: TEST_ULIDS.videoBooking1,
};

// ---------------------------------------------------------------------------
// Paginated list helpers
// ---------------------------------------------------------------------------

export function paginatedResponse(items: unknown[], total?: number) {
  return {
    items,
    total: total ?? items.length,
    page: 1,
    per_page: 20,
    has_next: false,
    has_prev: false,
  };
}
