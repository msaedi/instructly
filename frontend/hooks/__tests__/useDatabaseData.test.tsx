import { act, renderHook, waitFor } from '@testing-library/react';

import { useDatabaseData } from '../useDatabaseData';
import { databaseApi } from '@/lib/databaseApi';
import { logger } from '@/lib/logger';

jest.mock('@/lib/databaseApi', () => ({
  databaseApi: {
    getStats: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    error: jest.fn(),
  },
}));

const getStatsMock = databaseApi.getStats as jest.Mock;
const loggerErrorMock = logger.error as jest.Mock;

describe('useDatabaseData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches database stats on mount', async () => {
    const stats = { status: 'ok', pool: { size: 10 } };
    getStatsMock.mockResolvedValue(stats);

    const { result } = renderHook(() => useDatabaseData('token-123'));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getStatsMock).toHaveBeenCalledWith('token-123');
    expect(result.current.data).toEqual(stats);
  });

  it('uses an empty token when token is null', async () => {
    getStatsMock.mockResolvedValue({ status: 'ok' });

    const { result } = renderHook(() => useDatabaseData(null));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getStatsMock).toHaveBeenCalledWith('');
  });

  it('sets error state and logs when fetch fails', async () => {
    getStatsMock.mockRejectedValueOnce(new Error('Database error'));

    const { result } = renderHook(() => useDatabaseData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Database error');
    expect(loggerErrorMock).toHaveBeenCalledWith(
      'Failed to fetch database data',
      expect.any(Error)
    );
  });

  it('refetch triggers another request cycle', async () => {
    getStatsMock.mockResolvedValue({ status: 'ok' });

    const { result } = renderHook(() => useDatabaseData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refetch();
    });

    expect(getStatsMock).toHaveBeenCalledTimes(2);
  });

  it('keeps error null after successful fetch', async () => {
    getStatsMock.mockResolvedValue({ status: 'ok' });

    const { result } = renderHook(() => useDatabaseData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
  });

  it('uses fallback error message when thrown value is not an Error instance (line 32)', async () => {
    // Throw a string instead of an Error
    getStatsMock.mockRejectedValueOnce('raw string error');

    const { result } = renderHook(() => useDatabaseData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Should use the fallback message, not the thrown string
    expect(result.current.error).toBe('Failed to fetch database data');
    expect(loggerErrorMock).toHaveBeenCalledWith(
      'Failed to fetch database data',
      'raw string error'
    );
  });

  it('uses fallback error message when thrown value is a number', async () => {
    // Throw a number to verify the non-Error branch
    getStatsMock.mockRejectedValueOnce(42);

    const { result } = renderHook(() => useDatabaseData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Failed to fetch database data');
  });

  it('auto-refreshes on interval tick and handles a rejected fetch gracefully', async () => {
    jest.useFakeTimers();

    const stats = { status: 'ok', pool: { size: 10 } };
    getStatsMock.mockResolvedValue(stats);

    const { result } = renderHook(() => useDatabaseData('token-123'));

    // Wait for initial fetch
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getStatsMock).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(stats);

    // Make the next interval fetch reject to hunt for unhandled rejections
    getStatsMock.mockRejectedValueOnce(new Error('Connection refused'));

    // Advance 30 seconds to trigger the interval callback
    await act(async () => {
      jest.advanceTimersByTime(30 * 1000);
    });

    // Should have called getStats a second time via the interval
    await waitFor(() => expect(getStatsMock).toHaveBeenCalledTimes(2));

    // Error state should be set, not thrown
    expect(result.current.error).toBe('Connection refused');
    expect(loggerErrorMock).toHaveBeenCalledWith(
      'Failed to fetch database data',
      expect.any(Error)
    );

    jest.useRealTimers();
  });
});
