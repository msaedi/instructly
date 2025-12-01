import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useMessageThread } from '@/components/instructor/messages/hooks/useMessageThread';
import type { ConversationEntry } from '@/components/instructor/messages/types';

// Mock the API services
const mockUseMessageHistory = jest.fn();
const mockSendMessageImperative = jest.fn();
const mockMarkMessagesAsReadImperative = jest.fn();

jest.mock('@/src/api/services/messages', () => ({
  useMessageHistory: (...args: unknown[]) => mockUseMessageHistory(...args),
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
  const renderWithProps = (conversations: ConversationEntry[]) =>
    renderHook(
      ({ convos }) =>
        useMessageThread({
          currentUserId,
          conversations: convos,
          setConversations: setConversationsMock,
        }),
      { wrapper: createWrapper(), initialProps: { convos: conversations } }
    );

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

    mockUseMessageHistory.mockImplementation((bookingId: string) => {
      if (!bookingId) {
        return { data: undefined, isLoading: false, error: undefined };
      }
      return {
        data: {
          messages: [
            {
              id: 'msg1',
              content: 'Hello',
              sender_id: 'student1',
              created_at: '2024-01-01T12:00:00Z',
              updated_at: '2024-01-01T12:00:00Z',
              booking_id: bookingId,
            },
          ],
        },
        isLoading: false,
        error: undefined,
      };
    });

    mockMarkMessagesAsReadImperative.mockResolvedValue({});
  });

  describe('conversation switching', () => {
    it('loads history for the selected conversation and switches cleanly', async () => {
      mockUseMessageHistory.mockImplementation((bookingId: string) => {
        if (!bookingId) return { data: undefined, isLoading: false, error: undefined };
        if (bookingId === 'booking1') {
          return {
            data: {
              messages: [
                {
                  id: 'msg1',
                  content: 'Hello from conv1',
                  sender_id: 'student1',
                  created_at: '2024-01-01T12:00:00Z',
                  updated_at: '2024-01-01T12:00:00Z',
                  booking_id: bookingId,
                },
              ],
            },
            isLoading: false,
            error: undefined,
          };
        }
        return {
          data: {
            messages: [
              {
                id: 'msg2',
                content: 'Hello from conv2',
                sender_id: 'student2',
                created_at: '2024-01-01T12:00:00Z',
                updated_at: '2024-01-01T12:00:00Z',
                booking_id: bookingId,
              },
            ],
          },
          isLoading: false,
          error: undefined,
        };
      });

      const { result } = renderWithProps([mockConversation, mockConversation2]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages[0]?.text).toBe('Hello from conv1');
      });

      await act(async () => {
        result.current.loadThreadMessages('conv2', mockConversation2, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages[0]?.text).toBe('Hello from conv2');
      });

      const callsForBooking1 = mockUseMessageHistory.mock.calls.filter((call) => call[0] === 'booking1');
      const callsForBooking2 = mockUseMessageHistory.mock.calls.filter((call) => call[0] === 'booking2');
      expect(callsForBooking1.length).toBeGreaterThan(0);
      expect(callsForBooking2.length).toBeGreaterThan(0);
    });

    it('reuses cached messages when reloading the same conversation', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      expect(result.current.threadMessages.length).toBe(1);
    });
  });

  describe('cache invalidation', () => {
    it('should export invalidateConversationCache function', () => {
      const { result } = renderWithProps([mockConversation]);

      expect(typeof result.current.invalidateConversationCache).toBe('function');
    });

    it('should allow refetch after cache invalidation', async () => {
      const { result } = renderWithProps([mockConversation]);

      // Initial load
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(
          mockUseMessageHistory.mock.calls.some(
            (call) => call[0] === 'booking1' && call[3] === true
          )
        ).toBe(true);
      });

      const callsBefore = mockUseMessageHistory.mock.calls.length;

      // Invalidate and reload
      await act(async () => {
        result.current.invalidateConversationCache('conv1');
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(mockUseMessageHistory.mock.calls.length).toBeGreaterThan(callsBefore);
      });
    });
  });

  describe('message state management', () => {
    it('should update threadMessages when messages are loaded', async () => {
      const { result } = renderWithProps([mockConversation]);

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
      const { result } = renderWithProps([mockConversation]);

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
      mockUseMessageHistory.mockImplementation((bookingId: string) => ({
        data: {
          messages: [
            {
              id: 'msg1',
              content: 'Unread message',
              sender_id: 'student1', // From student, not current user
              created_at: '2024-01-01T12:00:00Z',
              updated_at: '2024-01-01T12:00:00Z',
              booking_id: bookingId,
              read_by: [], // Not read by current user
            },
          ],
        },
        isLoading: false,
        error: undefined,
      }));

      const { result } = renderWithProps([mockConversation]);

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

  describe('staleness handling', () => {
    it('does not refetch when conversation is not stale and cache exists', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      const callCountBefore = mockUseMessageHistory.mock.calls.length;

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      expect(mockUseMessageHistory.mock.calls.length).toBeLessThanOrEqual(callCountBefore + 1);
    });

    it('refetches when conversation marked stale via newer latestMessageAt', async () => {
      const newerConversation = { ...mockConversation, latestMessageAt: Date.now() + 1000 };
      const { result, rerender } = renderHook(
        ({ convos }) =>
          useMessageThread({
            currentUserId,
            conversations: convos,
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper(), initialProps: { convos: [mockConversation] } }
      );

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      mockUseMessageHistory.mockClear();
      rerender({ convos: [newerConversation] });

      await act(async () => {
        result.current.loadThreadMessages('conv1', newerConversation, 'inbox');
      });

      expect(
        mockUseMessageHistory.mock.calls.some(
          (call) => call[0] === 'booking1' && call[3] === true
        )
      ).toBe(true);
    });
  });
});
