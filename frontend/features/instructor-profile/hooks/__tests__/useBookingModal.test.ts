import { renderHook, act } from '@testing-library/react';
import { useBookingModal } from '../useBookingModal';

describe('useBookingModal', () => {
  it('initializes with closed modal state', () => {
    const { result } = renderHook(() => useBookingModal());

    expect(result.current.isOpen).toBe(false);
    expect(result.current.selectedDate).toBeUndefined();
    expect(result.current.selectedTime).toBeUndefined();
    expect(result.current.selectedService).toBeUndefined();
    expect(result.current.selectedDuration).toBeUndefined();
  });

  it('opens modal without options', () => {
    const { result } = renderHook(() => useBookingModal());

    act(() => {
      result.current.openBookingModal();
    });

    expect(result.current.isOpen).toBe(true);
  });

  it('opens modal with date option', () => {
    const { result } = renderHook(() => useBookingModal());

    act(() => {
      result.current.openBookingModal({ date: '2025-01-20' });
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedDate).toBe('2025-01-20');
  });

  it('opens modal with time option', () => {
    const { result } = renderHook(() => useBookingModal());

    act(() => {
      result.current.openBookingModal({ time: '14:00' });
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedTime).toBe('14:00');
  });

  it('opens modal with service option', () => {
    const { result } = renderHook(() => useBookingModal());
    const mockService = { id: 'svc-1', name: 'Piano Lesson' };

    act(() => {
      result.current.openBookingModal({ service: mockService });
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedService).toEqual(mockService);
  });

  it('opens modal with duration option', () => {
    const { result } = renderHook(() => useBookingModal());

    act(() => {
      result.current.openBookingModal({ duration: 60 });
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedDuration).toBe(60);
  });

  it('opens modal with all options', () => {
    const { result } = renderHook(() => useBookingModal());
    const mockService = { id: 'svc-1', name: 'Guitar Lesson' };

    act(() => {
      result.current.openBookingModal({
        date: '2025-01-25',
        time: '10:30',
        service: mockService,
        duration: 45,
      });
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedDate).toBe('2025-01-25');
    expect(result.current.selectedTime).toBe('10:30');
    expect(result.current.selectedService).toEqual(mockService);
    expect(result.current.selectedDuration).toBe(45);
  });

  it('closes modal and resets all state', () => {
    const { result } = renderHook(() => useBookingModal());

    // Open with options
    act(() => {
      result.current.openBookingModal({
        date: '2025-01-20',
        time: '14:00',
        service: { id: 'svc-1' },
        duration: 60,
      });
    });

    expect(result.current.isOpen).toBe(true);

    // Close
    act(() => {
      result.current.closeBookingModal();
    });

    expect(result.current.isOpen).toBe(false);
    expect(result.current.selectedDate).toBeUndefined();
    expect(result.current.selectedTime).toBeUndefined();
    expect(result.current.selectedService).toBeUndefined();
    expect(result.current.selectedDuration).toBeUndefined();
  });

  it('can reopen modal after closing', () => {
    const { result } = renderHook(() => useBookingModal());

    act(() => {
      result.current.openBookingModal({ date: '2025-01-20' });
    });
    expect(result.current.isOpen).toBe(true);

    act(() => {
      result.current.closeBookingModal();
    });
    expect(result.current.isOpen).toBe(false);

    act(() => {
      result.current.openBookingModal({ date: '2025-01-25' });
    });
    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedDate).toBe('2025-01-25');
  });

  it('handles undefined option values correctly', () => {
    const { result } = renderHook(() => useBookingModal());

    act(() => {
      result.current.openBookingModal({
        date: undefined,
        time: undefined,
      });
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedDate).toBeUndefined();
    expect(result.current.selectedTime).toBeUndefined();
  });

  it('handles empty string date option', () => {
    const { result } = renderHook(() => useBookingModal());

    act(() => {
      result.current.openBookingModal({ date: '' });
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedDate).toBe('');
  });
});
