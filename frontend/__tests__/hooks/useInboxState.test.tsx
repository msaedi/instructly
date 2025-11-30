import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useInboxState } from '@/hooks/useInboxState';
import type { InboxState } from '@/hooks/useInboxState';

// Mock dependencies
const mockUsePageVisibility = jest.fn();
const mockUseAuthStatus = jest.fn();

jest.mock('@/hooks/usePageVisibility', () => ({
  usePageVisibility: () => mockUsePageVisibility(),
}));

jest.mock('@/hooks/queries/useAuth', () => ({
  useAuthStatus: () => mockUseAuthStatus(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => `http://localhost:3000${path}`,
}));

// Mock fetch
global.fetch = jest.fn();

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'TestWrapper';
  return Wrapper;
};

describe('useInboxState', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();

    // Default mocks
    mockUsePageVisibility.mockReturnValue(true);
    mockUseAuthStatus.mockReturnValue({ isAuthenticated: true });
  });

  afterEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();
  });

  it('should fetch inbox state on mount', async () => {
    const mockResponse: InboxState = {
      conversations: [
        {
          id: 'conv1',
          other_user: { id: 'user1', name: 'John' },
          unread_count: 2,
          last_message: { preview: 'Hello', at: '2024-01-01T12:00:00Z', is_mine: false },
        },
        {
          id: 'conv2',
          other_user: { id: 'user2', name: 'Jane' },
          unread_count: 0,
          last_message: null,
        },
      ],
      total_unread: 2,
      unread_conversations: 1,
    };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Map([['ETag', '"abc123"']]),
      json: () => Promise.resolve(mockResponse),
    });

    const { result } = renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.data).toEqual(mockResponse);
    });

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:3000/api/v1/messages/inbox-state',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
      })
    );
  });

  it('should return 304 and keep previous data when ETag matches', async () => {
    const mockResponse: InboxState = {
      conversations: [],
      total_unread: 0,
      unread_conversations: 0,
    };

    // First call returns data with ETag
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (key: string) => (key === 'ETag' ? '"abc123"' : null),
        },
        json: () => Promise.resolve(mockResponse),
      })
      // Second call returns 304
      .mockResolvedValueOnce({
        ok: true,
        status: 304,
        headers: {
          get: () => null,
        },
      });

    const { result } = renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    // Wait for initial data
    await waitFor(() => {
      expect(result.current.data).toEqual(mockResponse);
    });

    // Trigger refetch by advancing timers
    await jest.advanceTimersByTimeAsync(5000);

    // Wait for the second call (304 response)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    // Should have sent If-None-Match header with ETag
    expect(global.fetch).toHaveBeenLastCalledWith(
      'http://localhost:3000/api/v1/messages/inbox-state',
      expect.objectContaining({
        headers: expect.objectContaining({
          'If-None-Match': '"abc123"',
        }),
      })
    );

    // Should still have previous data (not null/undefined)
    await waitFor(() => {
      expect(result.current.data).toEqual(mockResponse);
    });
  });

  it('should include unread_conversations count', async () => {
    const mockResponse: InboxState = {
      conversations: [
        {
          id: 'conv1',
          other_user: { id: 'user1', name: 'John' },
          unread_count: 3,
          last_message: { preview: 'Hello', at: '2024-01-01T12:00:00Z', is_mine: false },
        },
        {
          id: 'conv2',
          other_user: { id: 'user2', name: 'Jane' },
          unread_count: 2,
          last_message: { preview: 'Hi', at: '2024-01-01T12:01:00Z', is_mine: false },
        },
        {
          id: 'conv3',
          other_user: { id: 'user3', name: 'Bob' },
          unread_count: 0,
          last_message: null,
        },
      ],
      total_unread: 5,
      unread_conversations: 2, // Only 2 conversations have unreads
    };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: {
        get: (key: string) => (key === 'ETag' ? '"abc123"' : null),
      },
      json: () => Promise.resolve(mockResponse),
    });

    const { result } = renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.data?.unread_conversations).toBe(2);
    });

    expect(result.current.data?.total_unread).toBe(5);
  });

  it('should not fetch when user is not authenticated', async () => {
    mockUseAuthStatus.mockReturnValue({ isAuthenticated: false });

    renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    // Wait a bit
    await jest.advanceTimersByTimeAsync(10000);

    // Should not have called fetch
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('should not fetch when page is not visible', async () => {
    mockUsePageVisibility.mockReturnValue(false);

    renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    // Wait a bit
    await jest.advanceTimersByTimeAsync(10000);

    // Should not have called fetch
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('should poll at active interval initially', async () => {
    const mockResponse: InboxState = {
      conversations: [],
      total_unread: 0,
      unread_conversations: 0,
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      headers: {
        get: (key: string) => (key === 'ETag' ? '"abc123"' : null),
      },
      json: () => Promise.resolve(mockResponse),
    });

    renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    // Wait for initial fetch
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    // Clear and advance by active interval (5 seconds)
    (global.fetch as jest.Mock).mockClear();
    await jest.advanceTimersByTimeAsync(5000);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
  });

  it('should switch to idle interval after multiple 304 responses', async () => {
    const mockResponse: InboxState = {
      conversations: [],
      total_unread: 0,
      unread_conversations: 0,
    };

    // First call returns data
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: {
        get: (key: string) => (key === 'ETag' ? '"abc123"' : null),
      },
      json: () => Promise.resolve(mockResponse),
    });

    const { result } = renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.data).toEqual(mockResponse);
      expect(result.current.isActive).toBe(true);
    });

    // Mock 304 responses
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 304,
      headers: {
        get: () => null,
      },
    });

    // Trigger 3 consecutive 304s (ACTIVITY_THRESHOLD)
    for (let i = 0; i < 3; i++) {
      (global.fetch as jest.Mock).mockClear();
      await jest.advanceTimersByTimeAsync(5000);
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled();
      });
    }

    // Should now be in idle mode
    await waitFor(() => {
      expect(result.current.isActive).toBe(false);
    });
  });

  it('should provide refresh function', async () => {
    const mockResponse: InboxState = {
      conversations: [],
      total_unread: 0,
      unread_conversations: 0,
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      headers: {
        get: (key: string) => (key === 'ETag' ? '"abc123"' : null),
      },
      json: () => Promise.resolve(mockResponse),
    });

    const { result } = renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.data).toEqual(mockResponse);
    });

    expect(typeof result.current.refresh).toBe('function');

    // Should be able to call refresh
    (global.fetch as jest.Mock).mockClear();
    result.current.refresh();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
  });

  it('should provide invalidate function', () => {
    const { result } = renderHook(() => useInboxState(), {
      wrapper: createWrapper(),
    });

    expect(typeof result.current.invalidate).toBe('function');
  });
});
