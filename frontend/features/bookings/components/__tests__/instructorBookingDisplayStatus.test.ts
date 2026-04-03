import {
  getInstructorBookingDisplayStatus,
  getInstructorBookingEndTime,
} from '../instructorBookingDisplayStatus';

describe('instructorBookingDisplayStatus', () => {
  it('uses UTC timestamps to derive In Progress when they are available', () => {
    const booking = {
      status: 'CONFIRMED',
      booking_date: '2026-04-02',
      start_time: '14:15:00',
      end_time: '15:15:00',
      lesson_timezone: 'America/New_York',
      duration_minutes: 60,
      booking_start_utc: '2026-04-02T18:15:00Z',
      booking_end_utc: '2026-04-02T19:15:00Z',
    };

    expect(
      getInstructorBookingDisplayStatus(booking, new Date('2026-04-02T18:30:00Z'))
    ).toBe('IN_PROGRESS');
    expect(getInstructorBookingEndTime(booking)?.toISOString()).toBe('2026-04-02T19:15:00.000Z');
  });

  it('falls back to lesson timezone when UTC timestamps are missing', () => {
    const booking = {
      status: 'CONFIRMED',
      booking_date: '2026-04-02',
      start_time: '18:15:00',
      end_time: '19:15:00',
      lesson_timezone: 'America/New_York',
      duration_minutes: 60,
      booking_start_utc: null,
      booking_end_utc: null,
    };

    expect(
      getInstructorBookingDisplayStatus(booking, new Date('2026-04-02T22:30:00Z'))
    ).toBe('IN_PROGRESS');
    expect(getInstructorBookingEndTime(booking)?.toISOString()).toBe('2026-04-02T23:15:00.000Z');
  });
});
