import { renderHook } from '@testing-library/react';

import { useGuestSessionCleanup } from '../useGuestSessionCleanup';
import { getGuestSessionId } from '@/lib/searchTracking';
import { logger } from '@/lib/logger';

jest.mock('@/lib/searchTracking', () => ({
  getGuestSessionId: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    error: jest.fn(),
  },
}));

const getGuestSessionIdMock = getGuestSessionId as jest.Mock;
const loggerDebugMock = logger.debug as jest.Mock;
const loggerErrorMock = logger.error as jest.Mock;

describe('useGuestSessionCleanup', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('logs when a guest session id is available', () => {
    getGuestSessionIdMock.mockReturnValue('guest-123');

    renderHook(() => useGuestSessionCleanup());

    expect(getGuestSessionIdMock).toHaveBeenCalledTimes(1);
    expect(loggerDebugMock).toHaveBeenCalledWith('Guest session initialized', {
      sessionId: 'guest-123',
    });
  });

  it('does not log when no session id exists', () => {
    getGuestSessionIdMock.mockReturnValue(null);

    renderHook(() => useGuestSessionCleanup());

    expect(loggerDebugMock).not.toHaveBeenCalled();
  });

  it('logs errors when session initialization fails', () => {
    getGuestSessionIdMock.mockImplementation(() => {
      throw new Error('Storage error');
    });

    renderHook(() => useGuestSessionCleanup());

    expect(loggerErrorMock).toHaveBeenCalledWith(
      'Error initializing guest session',
      expect.any(Error)
    );
  });

  it('runs the cleanup only once on mount', () => {
    getGuestSessionIdMock.mockReturnValue('guest-123');

    const { rerender } = renderHook(() => useGuestSessionCleanup());

    rerender();

    expect(getGuestSessionIdMock).toHaveBeenCalledTimes(1);
  });

  it('does not throw when cleanup succeeds', () => {
    getGuestSessionIdMock.mockReturnValue('guest-123');

    expect(() => renderHook(() => useGuestSessionCleanup())).not.toThrow();
  });
});
