/**
 * Tests for useConversations hook and useUpdateConversationState mutation
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useConversations, useUpdateConversationState } from '../useConversations';
import type { InboxState } from '@/hooks/useInboxState';

// Mock dependencies
const mockInvalidate = jest.fn();
const mockUseInboxState = jest.fn();
const mockSubscribe = jest.fn();

jest.mock('@/hooks/useInboxState', () => ({
  useInboxState: (options?: { stateFilter?: string; typeFilter?: string }) =>
    mockUseInboxState(options),
}));

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

describe('useConversations', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    // Default mock: SSE subscribe returns a cleanup function
    mockSubscribe.mockReturnValue(() => {});

    // Default mock: useInboxState returns empty data
    mockUseInboxState.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      invalidate: mockInvalidate,
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('filtering', () => {
    it('should fetch all active conversations when no filter', async () => {
      const mockData: InboxState = {
        conversations: [
          {
            id: 'booking1',
            other_user: { id: 'user1', name: 'John Doe' },
            unread_count: 2,
            last_message: {
              preview: 'Hello there',
              at: '2024-01-01T12:00:00Z',
              is_mine: false,
            },
          },
        ],
        total_unread: 2,
        unread_conversations: 1,
      };

      mockUseInboxState.mockReturnValue({
        data: mockData,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
            // No stateFilter - should fetch active conversations
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.conversations).toHaveLength(1);
      expect(result.current.conversations[0]?.name).toBe('John Doe');
      expect(mockUseInboxState).toHaveBeenCalledWith({
        stateFilter: undefined,
        typeFilter: undefined,
      });
    });

    it('should fetch only archived conversations when stateFilter is archived', async () => {
      const mockData: InboxState = {
        conversations: [
          {
            id: 'booking1',
            other_user: { id: 'user1', name: 'Archived User' },
            unread_count: 0,
            last_message: {
              preview: 'Old message',
              at: '2024-01-01T12:00:00Z',
              is_mine: true,
            },
          },
        ],
        total_unread: 0,
        unread_conversations: 0,
      };

      mockUseInboxState.mockReturnValue({
        data: mockData,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
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

      expect(result.current.conversations).toHaveLength(1);
      expect(result.current.conversations[0]?.name).toBe('Archived User');
      expect(mockUseInboxState).toHaveBeenCalledWith({
        stateFilter: 'archived',
        typeFilter: undefined,
      });
    });

    it('should fetch only trashed conversations when stateFilter is trashed', async () => {
      const mockData: InboxState = {
        conversations: [
          {
            id: 'booking1',
            other_user: { id: 'user1', name: 'Trashed User' },
            unread_count: 0,
            last_message: {
              preview: 'Deleted message',
              at: '2024-01-01T12:00:00Z',
              is_mine: false,
            },
          },
        ],
        total_unread: 0,
        unread_conversations: 0,
      };

      mockUseInboxState.mockReturnValue({
        data: mockData,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
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

      expect(result.current.conversations).toHaveLength(1);
      expect(result.current.conversations[0]?.name).toBe('Trashed User');
      expect(mockUseInboxState).toHaveBeenCalledWith({
        stateFilter: 'trashed',
        typeFilter: undefined,
      });
    });

    it('should filter by type when typeFilter is provided', async () => {
      const mockData: InboxState = {
        conversations: [
          {
            id: 'booking1',
            other_user: { id: 'user1', name: 'Student User' },
            unread_count: 1,
            last_message: null,
          },
        ],
        total_unread: 1,
        unread_conversations: 1,
      };

      mockUseInboxState.mockReturnValue({
        data: mockData,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
            typeFilter: 'student',
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.conversations).toHaveLength(1);
      expect(mockUseInboxState).toHaveBeenCalledWith({
        stateFilter: undefined,
        typeFilter: 'student',
      });
    });
  });

  describe('unread count', () => {
    it('should calculate unreadConversationsCount correctly', async () => {
      const mockData: InboxState = {
        conversations: [
          {
            id: 'booking1',
            other_user: { id: 'user1', name: 'User 1' },
            unread_count: 3,
            last_message: {
              preview: 'Hello',
              at: '2024-01-01T12:00:00Z',
              is_mine: false,
            },
          },
          {
            id: 'booking2',
            other_user: { id: 'user2', name: 'User 2' },
            unread_count: 2,
            last_message: {
              preview: 'Hi',
              at: '2024-01-01T12:01:00Z',
              is_mine: false,
            },
          },
          {
            id: 'booking3',
            other_user: { id: 'user3', name: 'User 3' },
            unread_count: 0,
            last_message: {
              preview: 'Read message',
              at: '2024-01-01T11:00:00Z',
              is_mine: true,
            },
          },
        ],
        total_unread: 5,
        unread_conversations: 2,
      };

      mockUseInboxState.mockReturnValue({
        data: mockData,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.totalUnread).toBe(5);
      expect(result.current.unreadConversationsCount).toBe(2);
      expect(result.current.unreadConversations).toHaveLength(2);
      expect(result.current.unreadConversations[0]?.unread).toBe(3);
      expect(result.current.unreadConversations[1]?.unread).toBe(2);
    });

    it('should handle zero unreads correctly', async () => {
      const mockData: InboxState = {
        conversations: [
          {
            id: 'booking1',
            other_user: { id: 'user1', name: 'User 1' },
            unread_count: 0,
            last_message: {
              preview: 'All read',
              at: '2024-01-01T12:00:00Z',
              is_mine: true,
            },
          },
        ],
        total_unread: 0,
        unread_conversations: 0,
      };

      mockUseInboxState.mockReturnValue({
        data: mockData,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.totalUnread).toBe(0);
      expect(result.current.unreadConversationsCount).toBe(0);
      expect(result.current.unreadConversations).toHaveLength(0);
    });
  });

  describe('SSE integration', () => {
    it('should subscribe to global SSE events and invalidate on message', async () => {
      let onMessageCallback: (() => void) | undefined;

      // Capture the onMessage callback
      mockSubscribe.mockImplementation((_conversationId: string, handlers: { onMessage: () => void }) => {
        onMessageCallback = handlers.onMessage;
        return () => {}; // Cleanup function
      });

      mockUseInboxState.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
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

      // Simulate SSE message
      expect(onMessageCallback).toBeDefined();
      onMessageCallback?.();

      // Should invalidate inbox state
      expect(mockInvalidate).toHaveBeenCalled();
    });
  });

  describe('loading and error states', () => {
    it('should return loading state when user is loading', () => {
      mockUseInboxState.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: false,
        invalidate: mockInvalidate,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: undefined,
            isLoadingUser: true, // User loading
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.isLoading).toBe(true);
    });

    it('should return loading state when inbox state is loading', () => {
      mockUseInboxState.mockReturnValue({
        data: undefined,
        isLoading: true, // Inbox loading
        isError: false,
        invalidate: mockInvalidate,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.isLoading).toBe(true);
    });

    it('should return error state when inbox state fails', () => {
      mockUseInboxState.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true, // Error state
        invalidate: mockInvalidate,
      });

      const { result } = renderHook(
        () =>
          useConversations({
            currentUserId: 'instructor1',
            isLoadingUser: false,
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.error).toBe('Unable to load conversations');
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

  it('should call API with correct parameters for archive', async () => {
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
        'http://localhost:3000/api/v1/messages/conversations/booking1/state',
        expect.objectContaining({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ state: 'archived' }),
        })
      );
    });
  });

  it('should call API with correct parameters for trash', async () => {
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
        'http://localhost:3000/api/v1/messages/conversations/booking2/state',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ state: 'trashed' }),
        })
      );
    });
  });

  it('should call API with correct parameters for restore', async () => {
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
        'http://localhost:3000/api/v1/messages/conversations/booking3/state',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ state: 'active' }),
        })
      );
    });
  });

  it('should invalidate inbox-state queries on success', async () => {
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
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['inbox-state'] });
    });
  });

  it('should handle API errors', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
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
