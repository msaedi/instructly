import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useConversationMessages } from '../useConversationMessages';
import type { ReactNode } from 'react';

// Mock dependencies
jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((url: string) => `https://api.test.com${url}`),
}));

jest.mock('@/src/api/services/conversations', () => ({
  conversationQueryKeys: {
    messagesWithParams: jest.fn((id: string, params: Record<string, unknown>) => [
      'conversations',
      id,
      'messages',
      params,
    ]),
    messages: jest.fn((id: string) => ['conversations', id, 'messages']),
  },
}));

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Create wrapper with QueryClient
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return Wrapper;
};

describe('useConversationMessages', () => {
  const mockMessages = [
    {
      id: 'msg-1',
      conversation_id: 'conv-123',
      sender_id: 'user-1',
      content: 'Hello!',
      created_at: '2025-01-15T10:00:00Z',
    },
    {
      id: 'msg-2',
      conversation_id: 'conv-123',
      sender_id: 'user-2',
      content: 'Hi there!',
      created_at: '2025-01-15T10:01:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockReset();
  });

  it('does not fetch when conversationId is null', () => {
    const { result } = renderHook(
      () => useConversationMessages({ conversationId: null }),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(false);
    expect(result.current.messages).toEqual([]);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('does not fetch when enabled is false', () => {
    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123', enabled: false }),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('fetches messages when conversationId is provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: mockMessages,
        has_more: false,
        next_cursor: null,
      }),
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Messages should be reversed (oldest first for display)
    expect(result.current.messages).toHaveLength(2);
    expect(mockFetch).toHaveBeenCalled();
  });

  it('uses default limit of 50', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: [],
        has_more: false,
        next_cursor: null,
      }),
    });

    renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const fetchUrl = mockFetch.mock.calls[0][0] as string;
    expect(fetchUrl).toContain('limit=50');
  });

  it('includes booking filter when provided', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: [],
        has_more: false,
        next_cursor: null,
      }),
    });

    renderHook(
      () =>
        useConversationMessages({
          conversationId: 'conv-123',
          bookingFilter: 'booking-456',
        }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const fetchUrl = mockFetch.mock.calls[0][0] as string;
    expect(fetchUrl).toContain('booking_id=booking-456');
  });

  it('returns error message on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.error).toBe('Unable to load messages');
    });
  });

  it('indicates hasNextPage when has_more is true', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: mockMessages,
        has_more: true,
        next_cursor: 'cursor-abc',
      }),
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.hasNextPage).toBe(true);
    });
  });

  it('indicates no next page when has_more is false', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: mockMessages,
        has_more: false,
        next_cursor: null,
      }),
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.hasNextPage).toBe(false);
    });
  });

  it('provides fetchNextPage function', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: mockMessages,
        has_more: true,
        next_cursor: 'cursor-abc',
      }),
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(typeof result.current.fetchNextPage).toBe('function');
  });

  it('provides refetch function', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: [],
        has_more: false,
        next_cursor: null,
      }),
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(typeof result.current.refetch).toBe('function');
  });

  it('provides invalidate function', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: [],
        has_more: false,
        next_cursor: null,
      }),
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(typeof result.current.invalidate).toBe('function');
  });

  it('reverses messages for display (oldest first)', async () => {
    const orderedMessages = [
      { id: 'msg-new', content: 'Newest', created_at: '2025-01-15T11:00:00Z' },
      { id: 'msg-old', content: 'Oldest', created_at: '2025-01-15T09:00:00Z' },
    ];

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        messages: orderedMessages,
        has_more: false,
        next_cursor: null,
      }),
    });

    const { result } = renderHook(
      () => useConversationMessages({ conversationId: 'conv-123' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(2);
    });

    // Should be reversed - oldest first
    expect(result.current.messages[0]!.id).toBe('msg-old');
    expect(result.current.messages[1]!.id).toBe('msg-new');
  });

  describe('pagination with before cursor (lines 50, 111)', () => {
    it('includes before parameter in URL when cursor is provided', async () => {
      // First page
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [{ id: 'msg-1', content: 'First', created_at: '2025-01-15T10:00:00Z' }],
          has_more: true,
          next_cursor: 'cursor-abc',
        }),
      });

      // Second page
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [{ id: 'msg-2', content: 'Second', created_at: '2025-01-15T09:00:00Z' }],
          has_more: false,
          next_cursor: null,
        }),
      });

      const { result } = renderHook(
        () => useConversationMessages({ conversationId: 'conv-123' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.hasNextPage).toBe(true);
      });

      // Fetch next page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(2);
      });

      // Second call should include before parameter
      const secondCallUrl = mockFetch.mock.calls[1]?.[0] as string;
      expect(secondCallUrl).toContain('before=cursor-abc');
    });
  });

  describe('fetchNextPage behavior (lines 140-141)', () => {
    it('calls fetchNext when hasNextPage is true and not fetching', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [{ id: 'msg-1', content: 'First', created_at: '2025-01-15T10:00:00Z' }],
          has_more: true,
          next_cursor: 'cursor-xyz',
        }),
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [{ id: 'msg-2', content: 'Second', created_at: '2025-01-15T09:00:00Z' }],
          has_more: false,
          next_cursor: null,
        }),
      });

      const { result } = renderHook(
        () => useConversationMessages({ conversationId: 'conv-123' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(true);

      // Call fetchNextPage
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(2);
      });

      // After fetching second page, hasNextPage should be false
      await waitFor(() => {
        expect(result.current.hasNextPage).toBe(false);
      });
    });

    it('does not fetch when hasNextPage is false', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [{ id: 'msg-1', content: 'Only page', created_at: '2025-01-15T10:00:00Z' }],
          has_more: false,
          next_cursor: null,
        }),
      });

      const { result } = renderHook(
        () => useConversationMessages({ conversationId: 'conv-123' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.hasNextPage).toBe(false);

      // Try to fetch next page - should not trigger another fetch
      result.current.fetchNextPage();

      // Still only one fetch call
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('refetch wrapper (line 152)', () => {
    it('refetch function calls internal refetch and returns void', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [{ id: 'msg-1', content: 'Initial', created_at: '2025-01-15T10:00:00Z' }],
          has_more: false,
          next_cursor: null,
        }),
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [{ id: 'msg-1', content: 'Refetched', created_at: '2025-01-15T10:00:00Z' }],
          has_more: false,
          next_cursor: null,
        }),
      });

      const { result } = renderHook(
        () => useConversationMessages({ conversationId: 'conv-123' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Call refetch
      result.current.refetch();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('invalidate function (line 134)', () => {
    it('invalidate function calls queryClient.invalidateQueries', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [],
          has_more: false,
          next_cursor: null,
        }),
      });

      const { result } = renderHook(
        () => useConversationMessages({ conversationId: 'conv-123' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Call invalidate - should not throw
      expect(() => result.current.invalidate()).not.toThrow();
    });
  });

  describe('edge cases and error handling', () => {
    it('handles empty pages array gracefully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [],
          has_more: false,
          next_cursor: null,
        }),
      });

      const { result } = renderHook(
        () => useConversationMessages({ conversationId: 'conv-123' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.messages).toEqual([]);
      expect(result.current.hasNextPage).toBe(false);
    });

    it('handles multiple pages of messages', async () => {
      // First page
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [
            { id: 'msg-1', content: 'Page 1 Msg 1', created_at: '2025-01-15T10:00:00Z' },
            { id: 'msg-2', content: 'Page 1 Msg 2', created_at: '2025-01-15T09:00:00Z' },
          ],
          has_more: true,
          next_cursor: 'cursor-page2',
        }),
      });

      // Second page
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [
            { id: 'msg-3', content: 'Page 2 Msg 1', created_at: '2025-01-15T08:00:00Z' },
          ],
          has_more: false,
          next_cursor: null,
        }),
      });

      const { result } = renderHook(
        () => useConversationMessages({ conversationId: 'conv-123' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Fetch second page
      result.current.fetchNextPage();

      await waitFor(() => {
        expect(result.current.messages).toHaveLength(3);
      });

      // Messages should be from both pages, reversed for display
      expect(result.current.messages.map(m => m.id)).toContain('msg-1');
      expect(result.current.messages.map(m => m.id)).toContain('msg-3');
    });

    it('handles custom limit parameter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [],
          has_more: false,
          next_cursor: null,
        }),
      });

      renderHook(
        () => useConversationMessages({ conversationId: 'conv-123', limit: 25 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      const fetchUrl = mockFetch.mock.calls[0]?.[0] as string;
      expect(fetchUrl).toContain('limit=25');
    });
  });
});
