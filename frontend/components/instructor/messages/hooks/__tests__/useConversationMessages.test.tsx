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
});
