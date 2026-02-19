import { renderHook, act } from '@testing-library/react';
import { useCountdown } from '../useCountdown';

describe('useCountdown', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-01-15T12:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns correct seconds left for a future date', () => {
    const target = new Date('2026-01-15T12:01:30Z'); // 90 seconds in the future
    const { result } = renderHook(() => useCountdown(target));

    expect(result.current.secondsLeft).toBe(90);
    expect(result.current.isExpired).toBe(false);
  });

  it('returns isExpired=true for null target', () => {
    const { result } = renderHook(() => useCountdown(null));

    expect(result.current.secondsLeft).toBe(0);
    expect(result.current.isExpired).toBe(true);
  });

  it('returns isExpired=true for a past date', () => {
    const pastDate = new Date('2026-01-15T11:00:00Z'); // 1 hour ago
    const { result } = renderHook(() => useCountdown(pastDate));

    expect(result.current.secondsLeft).toBe(0);
    expect(result.current.isExpired).toBe(true);
  });

  it('updates every second as timers advance', () => {
    const target = new Date('2026-01-15T12:01:30Z'); // 90 seconds
    const { result } = renderHook(() => useCountdown(target));

    expect(result.current.secondsLeft).toBe(90);

    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.secondsLeft).toBe(89);

    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.secondsLeft).toBe(88);
  });

  it('formats MM:SS correctly for values under an hour', () => {
    const target = new Date('2026-01-15T12:01:30Z'); // 90 seconds
    const { result } = renderHook(() => useCountdown(target));

    expect(result.current.formatted).toBe('01:30');
  });

  it('formats HH:MM:SS for values >= 3600 seconds', () => {
    const target = new Date('2026-01-15T13:01:01Z'); // 3661 seconds
    const { result } = renderHook(() => useCountdown(target));

    expect(result.current.secondsLeft).toBe(3661);
    expect(result.current.formatted).toBe('01:01:01');
  });

  it('returns "00:00" when expired', () => {
    const pastDate = new Date('2026-01-15T11:59:00Z');
    const { result } = renderHook(() => useCountdown(pastDate));

    expect(result.current.formatted).toBe('00:00');
  });

  it('handles invalid date string and returns expired', () => {
    const { result } = renderHook(() => useCountdown('not-a-date'));

    expect(result.current.secondsLeft).toBe(0);
    expect(result.current.isExpired).toBe(true);
    expect(result.current.formatted).toBe('00:00');
  });

  it('stops interval when countdown reaches 0', () => {
    const target = new Date('2026-01-15T12:00:03Z'); // 3 seconds
    const { result } = renderHook(() => useCountdown(target));

    expect(result.current.secondsLeft).toBe(3);

    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.secondsLeft).toBe(2);

    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.secondsLeft).toBe(1);

    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.secondsLeft).toBe(0);
    expect(result.current.isExpired).toBe(true);

    // Advance further — secondsLeft should remain 0 (interval cleared)
    act(() => {
      jest.advanceTimersByTime(3000);
    });
    expect(result.current.secondsLeft).toBe(0);
  });

  it('accepts an ISO date string as target', () => {
    const { result } = renderHook(() => useCountdown('2026-01-15T12:01:30Z'));

    expect(result.current.secondsLeft).toBe(90);
    expect(result.current.isExpired).toBe(false);
    expect(result.current.formatted).toBe('01:30');
  });

  it('shares one ticker across hook instances and tears down when idle', () => {
    const setIntervalSpy = jest.spyOn(global, 'setInterval');
    const clearIntervalSpy = jest.spyOn(global, 'clearInterval');
    const setBaseline = setIntervalSpy.mock.calls.length;
    const clearBaseline = clearIntervalSpy.mock.calls.length;

    const target = new Date('2026-01-15T12:01:30Z');
    const hookA = renderHook(() => useCountdown(target));
    const hookB = renderHook(() => useCountdown(target));

    expect(setIntervalSpy.mock.calls.length - setBaseline).toBe(1);

    hookA.unmount();
    expect(clearIntervalSpy.mock.calls.length - clearBaseline).toBe(0);

    hookB.unmount();
    expect(clearIntervalSpy.mock.calls.length - clearBaseline).toBe(1);

    setIntervalSpy.mockRestore();
    clearIntervalSpy.mockRestore();
  });
});
