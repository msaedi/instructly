import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useMessageThread } from '@/components/instructor/messages/hooks/useMessageThread';
import type { ConversationEntry } from '@/components/instructor/messages/types';

// Mock the API services
const mockFetchMessageHistory = jest.fn();
const mockSendMessageImperative = jest.fn();
const mockMarkMessagesAsReadImperative = jest.fn();

jest.mock('@/src/api/services/messages', () => ({
  fetchMessageHistory: (...args: unknown[]) => mockFetchMessageHistory(...args),
  sendMessageImperative: (...args: unknown[]) => mockSendMessageImperative(...args),
  markMessagesAsReadImperative: (...args: unknown[]) => mockMarkMessagesAsReadImperative(...args),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'TestWrapper';
  return Wrapper;
};

describe('useMessageThread', () => {
  const currentUserId = 'instructor1';
  let setConversationsMock: jest.Mock;

  const mockConversation: ConversationEntry = {
    id: 'conv1',
    studentId: 'student1',
    name: 'John Student',
    lastMessage: '',
    timestamp: '',
    unread: 0,
    avatar: '',
    type: 'student' as const,
    bookingIds: ['booking1'],
    primaryBookingId: 'booking1',
    instructorId: 'instructor1',
    latestMessageAt: Date.now(),
  };

  const mockConversation2: ConversationEntry = {
    id: 'conv2',
    studentId: 'student2',
    name: 'Jane Student',
    lastMessage: '',
    timestamp: '',
    unread: 0,
    avatar: '',
    type: 'student' as const,
    bookingIds: ['booking2'],
    primaryBookingId: 'booking2',
    instructorId: 'instructor1',
    latestMessageAt: Date.now(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    setConversationsMock = jest.fn();

    mockFetchMessageHistory.mockResolvedValue({
      messages: [
        {
          id: 'msg1',
          content: 'Hello',
          sender_id: 'student1',
          created_at: '2024-01-01T12:00:00Z',
          updated_at: '2024-01-01T12:00:00Z',
          booking_id: 'booking1',
        },
      ],
    });

    mockMarkMessagesAsReadImperative.mockResolvedValue({});
  });

  describe('conversation switching', () => {
    it('should fetch fresh messages when switching conversations', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation, mockConversation2],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      // Load first conversation
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        await waitFor(() => {
          expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
        });
      });

      // Switch to second conversation
      mockFetchMessageHistory.mockResolvedValueOnce({
        messages: [
          {
            id: 'msg2',
            content: 'Hello from conv2',
            sender_id: 'student2',
            created_at: '2024-01-01T12:00:00Z',
            updated_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking2',
          },
        ],
      });

      await act(async () => {
        result.current.loadThreadMessages('conv2', mockConversation2, 'inbox');
        await waitFor(() => {
          expect(mockFetchMessageHistory).toHaveBeenCalledTimes(2);
        });
      });

      // Should have called API twice - once for each conversation
      expect(mockFetchMessageHistory).toHaveBeenCalledWith('booking1', { limit: 100, offset: 0 });
      expect(mockFetchMessageHistory).toHaveBeenCalledWith('booking2', { limit: 100, offset: 0 });
    });

    it('should invalidate cache before loading on switch', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      // Load conversation
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        await waitFor(() => {
          expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
        });
      });

      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);

      // Try to load again without invalidating - should NOT refetch (cached)
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      // Should still be 1 call (not refetched)
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);

      // Now invalidate and reload
      await act(async () => {
        result.current.invalidateConversationCache('conv1');
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        await waitFor(() => {
          expect(mockFetchMessageHistory).toHaveBeenCalledTimes(2);
        });
      });

      // Should have fetched again after invalidation
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(2);
    });

    it('should not fetch repeatedly on re-renders (no infinite loop)', async () => {
      const { result, rerender } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        await waitFor(() => {
          expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
        });
      });

      const initialCallCount = mockFetchMessageHistory.mock.calls.length;

      // Simulate multiple re-renders (like parent state changes)
      rerender();
      rerender();
      rerender();
      rerender();
      rerender();

      // Should NOT have made additional fetch calls
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(initialCallCount);
    });

    it('should prevent concurrent fetches for the same conversation', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      // Make API slow to simulate race condition
      let resolvePromise: (value: unknown) => void;
      const slowPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      mockFetchMessageHistory.mockReturnValue(slowPromise);

      // Trigger multiple loads rapidly
      act(() => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      // Resolve the promise
      act(() => {
        resolvePromise!({
          messages: [
            {
              id: 'msg1',
              content: 'Hello',
              sender_id: 'student1',
              created_at: '2024-01-01T12:00:00Z',
              updated_at: '2024-01-01T12:00:00Z',
              booking_id: 'booking1',
            },
          ],
        });
      });

      await waitFor(() => {
        // Should only call API once despite multiple attempts
        expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe('cache invalidation', () => {
    it('should export invalidateConversationCache function', () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      expect(typeof result.current.invalidateConversationCache).toBe('function');
    });

    it('should allow refetch after cache invalidation', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      // Initial load
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        await waitFor(() => {
          expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
        });
      });

      // Second load without invalidation - should not refetch
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);

      // Invalidate and reload
      await act(async () => {
        result.current.invalidateConversationCache('conv1');
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        await waitFor(() => {
          expect(mockFetchMessageHistory).toHaveBeenCalledTimes(2);
        });
      });

      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(2);
    });
  });

  describe('message state management', () => {
    it('should update threadMessages when messages are loaded', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      expect(result.current.threadMessages).toEqual([]);

      act(() => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBeGreaterThan(0);
      });

      expect(result.current.threadMessages.length).toBe(1);
      expect(result.current.threadMessages[0]?.text).toBe('Hello');
    });

    it('should cache messages by thread', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      act(() => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.messagesByThread['conv1']).toBeDefined();
      });

      expect(result.current.messagesByThread['conv1']?.length).toBe(1);
      expect(result.current.messagesByThread['conv1']?.[0]?.text).toBe('Hello');
    });
  });

  describe('unread count management', () => {
    it('should update conversation unread count after loading', async () => {
      mockFetchMessageHistory.mockResolvedValueOnce({
        messages: [
          {
            id: 'msg1',
            content: 'Unread message',
            sender_id: 'student1', // From student, not current user
            created_at: '2024-01-01T12:00:00Z',
            updated_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
            read_by: [], // Not read by current user
          },
        ],
      });

      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
        await waitFor(() => {
          expect(mockMarkMessagesAsReadImperative).toHaveBeenCalled();
        });
      });

      // Should have called setConversations to update unread count
      expect(setConversationsMock).toHaveBeenCalled();
    });
  });
});
