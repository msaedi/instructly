import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { fetchWithAuth } from '@/lib/api';
import { useProfilePictureUrls } from '../useProfilePictureUrls';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

const fetchMock = fetchWithAuth as jest.MockedFunction<typeof fetchWithAuth>;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('useProfilePictureUrls', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    fetchMock.mockReset();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('batches multiple ids into a single request', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        urls: {
          'user-a': 'https://cdn/avatar/a',
          'user-b': null,
        },
      }),
    } as Response);

    const { result } = renderHook(() => useProfilePictureUrls(['user-a', 'user-b']), {
      wrapper: createWrapper(),
    });

    expect(result.current['user-a']).toBeNull();
    expect(result.current['user-b']).toBeNull();

    act(() => {
      jest.runOnlyPendingTimers();
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const firstCall = fetchMock.mock.calls[0];
    if (!firstCall) {
      throw new Error('fetchWithAuth was not called');
    }
    const [requestUrl] = firstCall;
    expect(requestUrl).toContain('/api/v1/users/profile-picture-urls?');
    await waitFor(() => {
      expect(result.current['user-a']).toBe('https://cdn/avatar/a');
    });
    expect(result.current['user-b']).toBeNull();
  });

  it('falls back to placeholders when the request fails', async () => {
    fetchMock.mockRejectedValue(new Error('network error'));

    const { result } = renderHook(() => useProfilePictureUrls(['user-x']), {
      wrapper: createWrapper(),
    });

    act(() => {
      jest.runOnlyPendingTimers();
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current['user-x']).toBeNull();
  });
});
