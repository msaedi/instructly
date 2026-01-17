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
  location_type: 'neutral',
  ...overrides,
});

describe('useBookedSlots', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
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
});
