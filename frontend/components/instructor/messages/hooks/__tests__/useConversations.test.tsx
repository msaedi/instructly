/**
 * Tests for useConversations hook and useUpdateConversationState mutation
 *
 * Phase 4: Updated to test the new /api/v1/conversations endpoint.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useConversations, useUpdateConversationState } from '../useConversations';
import type { ConversationListResponse } from '@/types/conversation';

// Mock dependencies
const mockSubscribe = jest.fn();

jest.mock('@/providers/UserMessageStreamProvider', () => ({
  useMessageStream: () => ({
    subscribe: mockSubscribe,
  }),
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

// Helper to create mock conversation list response
const createMockConversationListResponse = (
  conversations: ConversationListResponse['conversations'] = []
): ConversationListResponse => ({
  conversations,
  next_cursor: null,
});

describe('useConversations', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    // Default mock: SSE subscribe returns a cleanup function
    mockSubscribe.mockReturnValue(() => {});

    // Default mock: fetch returns empty conversation list
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(createMockConversationListResponse()),
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('filtering', () => {
    it('should fetch active conversations by default', async () => {
      const mockData = createMockConversationListResponse([
        {
          id: 'conv1',
          other_user: { id: 'user1', first_name: 'John', last_initial: 'D' },
          unread_count: 2,
          last_message: {
            content: 'Hello there',
            created_at: '2024-01-01T12:00:00Z',
            is_from_me: false,
          },
          upcoming_booking_count: 0,
          state: 'active',
        },
      ]);

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockData),
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.conversations).toHaveLength(1);
      });

      expect(result.current.conversations[0]?.name).toBe('John D.');
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/conversations'),
        expect.any(Object)
      );
    });

    it('should fetch archived conversations when stateFilter is archived', async () => {
      const mockData = createMockConversationListResponse([
        {
          id: 'conv1',
          other_user: { id: 'user1', first_name: 'Archived', last_initial: 'U' },
          unread_count: 0,
          last_message: {
            content: 'Old message',
            created_at: '2024-01-01T12:00:00Z',
            is_from_me: true,
          },
          upcoming_booking_count: 0,
          state: 'archived',
        },
      ]);

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockData),
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
            stateFilter: 'archived',
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.conversations).toHaveLength(1);
      });

      expect(result.current.conversations[0]?.name).toBe('Archived U.');
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('state=archived'),
        expect.any(Object)
      );
    });

    it('should fetch trashed conversations when stateFilter is trashed', async () => {
      const mockData = createMockConversationListResponse([
        {
          id: 'conv1',
          other_user: { id: 'user1', first_name: 'Trashed', last_initial: 'U' },
          unread_count: 0,
          last_message: {
            content: 'Deleted message',
            created_at: '2024-01-01T12:00:00Z',
            is_from_me: false,
          },
          upcoming_booking_count: 0,
          state: 'trashed',
        },
      ]);

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockData),
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
            stateFilter: 'trashed',
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.conversations).toHaveLength(1);
      });

      expect(result.current.conversations[0]?.name).toBe('Trashed U.');
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('state=trashed'),
        expect.any(Object)
      );
    });

    it('should filter out platform type when typeFilter is platform', async () => {
      const mockData = createMockConversationListResponse([
        {
          id: 'conv1',
          other_user: { id: 'user1', first_name: 'Student', last_initial: 'U' },
          unread_count: 1,
          last_message: null,
          upcoming_booking_count: 0,
          state: 'active',
        },
      ]);

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockData),
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
            typeFilter: 'platform', // Platform type not supported yet
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Platform filter filters out all conversations (not supported in new API)
      expect(result.current.conversations).toHaveLength(0);
    });
  });

  describe('unread count', () => {
    it('should calculate unreadConversationsCount correctly', async () => {
      const mockData = createMockConversationListResponse([
        {
          id: 'conv1',
          other_user: { id: 'user1', first_name: 'User', last_initial: '1' },
          unread_count: 3,
          last_message: {
            content: 'Hello',
            created_at: '2024-01-01T12:00:00Z',
            is_from_me: false,
          },
          upcoming_booking_count: 0,
          state: 'active',
        },
        {
          id: 'conv2',
          other_user: { id: 'user2', first_name: 'User', last_initial: '2' },
          unread_count: 2,
          last_message: {
            content: 'Hi',
            created_at: '2024-01-01T12:01:00Z',
            is_from_me: false,
          },
          upcoming_booking_count: 0,
          state: 'active',
        },
        {
          id: 'conv3',
          other_user: { id: 'user3', first_name: 'User', last_initial: '3' },
          unread_count: 0,
          last_message: {
            content: 'Read message',
            created_at: '2024-01-01T11:00:00Z',
            is_from_me: true,
          },
          upcoming_booking_count: 0,
          state: 'active',
        },
      ]);

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockData),
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.conversations).toHaveLength(3);
      });

      expect(result.current.totalUnread).toBe(5);
      expect(result.current.unreadConversationsCount).toBe(2);
      expect(result.current.unreadConversations).toHaveLength(2);
    });

    it('should handle zero unreads correctly', async () => {
      const mockData = createMockConversationListResponse([
        {
          id: 'conv1',
          other_user: { id: 'user1', first_name: 'User', last_initial: '1' },
          unread_count: 0,
          last_message: {
            content: 'All read',
            created_at: '2024-01-01T12:00:00Z',
            is_from_me: true,
          },
          upcoming_booking_count: 0,
          state: 'active',
        },
      ]);

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockData),
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.conversations).toHaveLength(1);
      });

      expect(result.current.totalUnread).toBe(0);
      expect(result.current.unreadConversationsCount).toBe(0);
      expect(result.current.unreadConversations).toHaveLength(0);
    });
  });

  describe('SSE integration', () => {
    it('should subscribe to global SSE events', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(createMockConversationListResponse()),
      });

      renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      // Should subscribe to global events
      expect(mockSubscribe).toHaveBeenCalledWith('__global__', expect.any(Object));
    });
  });

  describe('loading and error states', () => {
    it('should return loading state when user is loading', () => {
      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: undefined,
            isLoadingUser: true,
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.isLoading).toBe(true);
    });

    it('should return error state when fetch fails', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.error).toBe('Unable to load conversations');
      });
    });
  });
});

describe('useUpdateConversationState', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should call new API endpoint for archive', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ state: 'archived' }),
    });

    const { result } = renderHook(() => useUpdateConversationState(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ bookingId: 'booking1', state: 'archived' });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/v1/conversations/booking1/state',
        expect.objectContaining({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ state: 'archived' }),
        })
      );
    });
  });

  it('should call new API endpoint for trash', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ state: 'trashed' }),
    });

    const { result } = renderHook(() => useUpdateConversationState(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ bookingId: 'booking2', state: 'trashed' });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/v1/conversations/booking2/state',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ state: 'trashed' }),
        })
      );
    });
  });

  it('should call new API endpoint for restore', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ state: 'active' }),
    });

    const { result } = renderHook(() => useUpdateConversationState(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ bookingId: 'booking3', state: 'active' });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:3000/api/v1/conversations/booking3/state',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ state: 'active' }),
        })
      );
    });
  });

  it('should fall back to legacy endpoint on 404', async () => {
    // First call returns 404 (new endpoint not found)
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
      })
      // Second call succeeds (legacy endpoint)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ state: 'archived' }),
      });

    const { result } = renderHook(() => useUpdateConversationState(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ bookingId: 'booking1', state: 'archived' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Should have tried new endpoint first, then legacy
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch).toHaveBeenNthCalledWith(
      1,
      'http://localhost:3000/api/v1/conversations/booking1/state',
      expect.any(Object)
    );
    expect(global.fetch).toHaveBeenNthCalledWith(
      2,
      'http://localhost:3000/api/v1/messages/conversations/booking1/state',
      expect.any(Object)
    );
  });

  it('should invalidate conversation queries on success', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ state: 'archived' }),
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    Wrapper.displayName = 'TestWrapper';

    const { result } = renderHook(() => useUpdateConversationState(), {
      wrapper: Wrapper,
    });

    result.current.mutate({ bookingId: 'booking1', state: 'archived' });

    await waitFor(() => {
      // Should invalidate both new and legacy query keys
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['conversations'] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['inbox-state'] });
    });
  });

  it('should handle API errors', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

    const { result } = renderHook(() => useUpdateConversationState(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ bookingId: 'booking1', state: 'archived' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
      expect(result.current.error).toBeTruthy();
    });
  });
});
