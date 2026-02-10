import { renderHook, act } from '@testing-library/react';
import { useBookedSlots } from '../useBookedSlots';
import { fetchWithAuth } from '@/lib/api';
import type { BookedSlotPreview } from '@/types/booking';

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    fetchWithAuth: jest.fn(),
  };
});

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    error: jest.fn(),
    time: jest.fn(),
    timeEnd: jest.fn(),
  },
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;

const createSlot = (overrides: Partial<BookedSlotPreview> = {}): BookedSlotPreview => ({
  booking_id: 'booking-1',
  date: '2025-01-06',
  start_time: '09:00:00',
  end_time: '11:00:00',
  student_first_name: 'Jane',
  student_last_initial: 'D',
  service_name: 'Math',
  service_area_short: 'NYC',
  duration_minutes: 120,
  location_type: 'neutral_location',
  ...overrides,
});

describe('useBookedSlots', () => {
  const originalEnv = process.env.NODE_ENV;

  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  afterEach(() => {
    Object.defineProperty(process.env, 'NODE_ENV', {
      value: originalEnv,
      writable: true,
      configurable: true,
    });
    jest.useRealTimers();
  });

  it('fetches bookings and exposes slot helpers', async () => {
    const slot = createSlot();
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
    });

    const { result } = renderHook(() => useBookedSlots());

    await act(async () => {
      await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
    });

    expect(result.current.bookedSlots).toEqual([slot]);
    expect(result.current.isSlotBooked('2025-01-06', 9)).toBe(true);
    expect(result.current.getBookingForSlot('2025-01-06', 10)).toEqual(slot);
    expect(result.current.getBookingsForDate('2025-01-06')).toHaveLength(1);
    expect(result.current.hasBookingInRange('2025-01-06', 8, 9)).toBe(false);
    expect(result.current.hasBookingInRange('2025-01-06', 9, 12)).toBe(true);

    act(() => {
      result.current.handleBookingClick('booking-1');
    });

    expect(result.current.selectedBookingId).toBe('booking-1');
    expect(result.current.showBookingPreview).toBe(true);

    act(() => {
      result.current.closeBookingPreview();
    });

    expect(result.current.showBookingPreview).toBe(false);
    expect(result.current.selectedBookingId).toBeNull();
  });

  it('sets an error when fetch fails', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      json: jest.fn(),
    });

    const { result } = renderHook(() => useBookedSlots());

    await act(async () => {
      await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
    });

    expect(result.current.bookingError).toBe('Failed to load bookings');
    expect(result.current.bookedSlots).toEqual([]);
    expect(result.current.isLoadingBookings).toBe(false);
  });

  it('handles fetch errors gracefully', async () => {
    fetchWithAuthMock.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useBookedSlots());

    await act(async () => {
      await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
    });

    expect(result.current.bookingError).toBe('Failed to load bookings');
    expect(result.current.bookedSlots).toEqual([]);
  });

  it('logs cache status in development mode', async () => {
    Object.defineProperty(process.env, 'NODE_ENV', {
      value: 'development',
      writable: true,
      configurable: true,
    });
    jest.useFakeTimers();

    const slot = createSlot();
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
    });

    const { result } = renderHook(() => useBookedSlots());

    await act(async () => {
      await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
    });

    act(() => {
      jest.advanceTimersByTime(30000);
    });

    const { logger } = jest.requireMock('@/lib/logger') as { logger: { debug: jest.Mock } };
    expect(logger.debug).toHaveBeenCalledWith(
      'Booking cache status',
      expect.objectContaining({ weekStart: expect.any(String) })
    );
  });

  it('handles null booked_slots in response data (not an array)', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ booked_slots: null }),
    });

    const { result } = renderHook(() => useBookedSlots());

    await act(async () => {
      await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
    });

    // When booked_slots is null, the Array.isArray check should return false
    // and the fallback empty array should be used
    expect(result.current.bookedSlots).toEqual([]);
    expect(result.current.bookingError).toBeNull();
    expect(result.current.isLoadingBookings).toBe(false);
  });

  it('handles undefined data in response (no booked_slots key)', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({}),
    });

    const { result } = renderHook(() => useBookedSlots());

    await act(async () => {
      await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
    });

    expect(result.current.bookedSlots).toEqual([]);
    expect(result.current.bookingError).toBeNull();
  });

  it('does not cache when enableCache is false', async () => {
    const slot = createSlot({ booking_id: 'no-cache-1' });
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
    });

    const { result } = renderHook(() => useBookedSlots({ enableCache: false }));

    const weekStart = new Date('2025-01-06T00:00:00Z');

    await act(async () => {
      await result.current.fetchBookedSlots(weekStart);
    });

    await act(async () => {
      await result.current.fetchBookedSlots(weekStart);
    });

    // Without caching, both fetches should hit the API
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(2);
  });

  it('does not log cache status in production mode', async () => {
    Object.defineProperty(process.env, 'NODE_ENV', {
      value: 'production',
      writable: true,
      configurable: true,
    });
    jest.useFakeTimers();

    const slot = createSlot();
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
    });

    const { result } = renderHook(() => useBookedSlots());

    await act(async () => {
      await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
    });

    const { logger } = jest.requireMock('@/lib/logger') as { logger: { debug: jest.Mock } };
    logger.debug.mockClear();

    act(() => {
      jest.advanceTimersByTime(30000);
    });

    // In production mode, cache status should not be logged
    const cacheStatusCalls = logger.debug.mock.calls.filter(
      (call: unknown[]) => call[0] === 'Booking cache status'
    );
    expect(cacheStatusCalls).toHaveLength(0);
  });

  it('uses cache and refresh bypasses it', async () => {
    const slot = createSlot({ booking_id: 'booking-2' });
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
    });
    const dateNowSpy = jest.spyOn(Date, 'now').mockReturnValue(0);

    const { result } = renderHook(() => useBookedSlots());
    const weekStart = new Date('2025-01-06T00:00:00Z');

    await act(async () => {
      await result.current.fetchBookedSlots(weekStart);
    });

    await act(async () => {
      await result.current.fetchBookedSlots(weekStart);
    });

    expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);

    dateNowSpy.mockReturnValue(600000);

    await act(async () => {
      await result.current.refreshBookings(weekStart);
    });

    expect(fetchWithAuthMock).toHaveBeenCalledTimes(2);
    dateNowSpy.mockRestore();
  });

  describe('overlapping bookings', () => {
    it('returns the first matching booking when multiple bookings overlap the same hour', async () => {
      const slot1 = createSlot({
        booking_id: 'booking-overlap-1',
        start_time: '09:00:00',
        end_time: '11:00:00',
      });
      const slot2 = createSlot({
        booking_id: 'booking-overlap-2',
        start_time: '10:00:00',
        end_time: '12:00:00',
      });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot1, slot2] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      // Hour 10 is covered by both bookings; getBookingForSlot returns the first match
      const booking = result.current.getBookingForSlot('2025-01-06', 10);
      expect(booking?.booking_id).toBe('booking-overlap-1');

      // Both hours should be marked booked
      expect(result.current.isSlotBooked('2025-01-06', 9)).toBe(true);
      expect(result.current.isSlotBooked('2025-01-06', 10)).toBe(true);
      expect(result.current.isSlotBooked('2025-01-06', 11)).toBe(true);
    });
  });

  describe('cross-midnight bookings', () => {
    it('handles booking where endHour equals startHour (zero-length)', async () => {
      // A booking from 10:00:00 to 10:00:00 covers zero hours
      const slot = createSlot({
        booking_id: 'booking-zero',
        start_time: '10:00:00',
        end_time: '10:00:00',
      });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      // Zero-length booking covers no hours
      expect(result.current.isSlotBooked('2025-01-06', 10)).toBe(false);
      expect(result.current.getBookingForSlot('2025-01-06', 10)).toBeNull();
    });

    it('handles booking where end_time is before start_time (invalid range)', async () => {
      // A booking from 10:00:00 to 08:00:00 - the loop condition h < endHour is never true
      const slot = createSlot({
        booking_id: 'booking-backwards',
        start_time: '10:00:00',
        end_time: '08:00:00',
      });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      // The loop `for h = 10; h < 8` never runs
      expect(result.current.isSlotBooked('2025-01-06', 10)).toBe(false);
      expect(result.current.isSlotBooked('2025-01-06', 9)).toBe(false);
    });
  });

  describe('empty booking arrays', () => {
    it('returns empty array from getBookingsForDate for dates with no bookings', async () => {
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      expect(result.current.getBookingsForDate('2025-01-06')).toEqual([]);
      expect(result.current.getBookingsForDate('2025-01-07')).toEqual([]);
    });

    it('returns false from hasBookingInRange for empty bookings', async () => {
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      expect(result.current.hasBookingInRange('2025-01-06', 0, 24)).toBe(false);
    });

    it('returns false from isSlotBooked for every hour when no bookings exist', async () => {
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      for (let h = 0; h < 24; h++) {
        expect(result.current.isSlotBooked('2025-01-06', h)).toBe(false);
      }
    });
  });

  describe('cache valid hit path', () => {
    it('returns cached data immediately without calling API when cache is fresh', async () => {
      const slot = createSlot({ booking_id: 'booking-cached' });
      fetchWithAuthMock.mockResolvedValue({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
      });
      const dateNowSpy = jest.spyOn(Date, 'now').mockReturnValue(1000);

      const { result } = renderHook(() => useBookedSlots({ enableCache: true, cacheDuration: 60000 }));
      const weekStart = new Date('2025-01-06T00:00:00Z');

      // First fetch populates cache
      await act(async () => {
        await result.current.fetchBookedSlots(weekStart);
      });

      expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
      expect(result.current.bookedSlots).toEqual([slot]);

      // Advance time but still within cache duration
      dateNowSpy.mockReturnValue(30000); // 29 seconds later (< 60s cacheDuration)

      // Second fetch should use cache
      await act(async () => {
        await result.current.fetchBookedSlots(weekStart);
      });

      // Should still only have 1 API call
      expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
      expect(result.current.bookedSlots).toEqual([slot]);

      dateNowSpy.mockRestore();
    });

    it('fetches fresh data when cache is expired', async () => {
      const slot = createSlot({ booking_id: 'booking-expire' });
      fetchWithAuthMock.mockResolvedValue({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
      });
      const dateNowSpy = jest.spyOn(Date, 'now').mockReturnValue(0);

      const { result } = renderHook(() => useBookedSlots({ enableCache: true, cacheDuration: 5000 }));
      const weekStart = new Date('2025-01-06T00:00:00Z');

      await act(async () => {
        await result.current.fetchBookedSlots(weekStart);
      });

      expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);

      // Advance time past cache duration
      dateNowSpy.mockReturnValue(10000); // 10 seconds later (> 5s cacheDuration)

      await act(async () => {
        await result.current.fetchBookedSlots(weekStart);
      });

      // Should have made a second API call because cache expired
      expect(fetchWithAuthMock).toHaveBeenCalledTimes(2);

      dateNowSpy.mockRestore();
    });
  });

  describe('getBookingsForDate with multiple dates', () => {
    it('returns only bookings for the requested date', async () => {
      const slot1 = createSlot({ booking_id: 'booking-d1', date: '2025-01-06' });
      const slot2 = createSlot({ booking_id: 'booking-d2', date: '2025-01-07' });
      const slot3 = createSlot({ booking_id: 'booking-d3', date: '2025-01-06' });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot1, slot2, slot3] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      const jan6Bookings = result.current.getBookingsForDate('2025-01-06');
      expect(jan6Bookings).toHaveLength(2);
      expect(jan6Bookings.map(b => b.booking_id)).toEqual(['booking-d1', 'booking-d3']);

      const jan7Bookings = result.current.getBookingsForDate('2025-01-07');
      expect(jan7Bookings).toHaveLength(1);
      expect(jan7Bookings[0]?.booking_id).toBe('booking-d2');

      const jan8Bookings = result.current.getBookingsForDate('2025-01-08');
      expect(jan8Bookings).toHaveLength(0);
    });
  });

  describe('hasBookingInRange edge cases', () => {
    it('returns false when range has zero width (startHour === endHour)', async () => {
      const slot = createSlot({
        start_time: '09:00:00',
        end_time: '11:00:00',
      });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      // Zero-width range should return false even if the hour is booked
      expect(result.current.hasBookingInRange('2025-01-06', 10, 10)).toBe(false);
    });

    it('returns true only when at least one hour in range is booked', async () => {
      const slot = createSlot({
        start_time: '14:00:00',
        end_time: '16:00:00',
      });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      // Range overlapping with booking
      expect(result.current.hasBookingInRange('2025-01-06', 13, 15)).toBe(true);
      // Range entirely before booking
      expect(result.current.hasBookingInRange('2025-01-06', 10, 14)).toBe(false);
      // Range entirely after booking
      expect(result.current.hasBookingInRange('2025-01-06', 16, 18)).toBe(false);
    });
  });

  describe('cache disabled and logging effect', () => {
    it('returns undefined from logging effect when cache is disabled', () => {
      Object.defineProperty(process.env, 'NODE_ENV', {
        value: 'development',
        writable: true,
        configurable: true,
      });
      jest.useFakeTimers();

      // Render with enableCache: false
      renderHook(() => useBookedSlots({ enableCache: false }));

      // The effect should return undefined (no interval to clean up)
      // and not set up a 30s interval
      const { logger } = jest.requireMock('@/lib/logger') as { logger: { debug: jest.Mock } };
      logger.debug.mockClear();

      act(() => {
        jest.advanceTimersByTime(30000);
      });

      // No cache status should be logged because enableCache is false
      const cacheStatusCalls = logger.debug.mock.calls.filter(
        (call: unknown[]) => call[0] === 'Booking cache status'
      );
      expect(cacheStatusCalls).toHaveLength(0);
    });
  });

  describe('getBookingForSlot with different dates', () => {
    it('returns null when date does not match any booking', async () => {
      const slot = createSlot({ date: '2025-01-06' });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ booked_slots: [slot] }),
      });

      const { result } = renderHook(() => useBookedSlots());

      await act(async () => {
        await result.current.fetchBookedSlots(new Date('2025-01-06T00:00:00Z'));
      });

      // Correct date, wrong hour
      expect(result.current.getBookingForSlot('2025-01-06', 8)).toBeNull();
      // Wrong date, correct hour
      expect(result.current.getBookingForSlot('2025-01-07', 9)).toBeNull();
    });
  });
});
