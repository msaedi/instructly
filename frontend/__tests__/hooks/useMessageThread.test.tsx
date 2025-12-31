import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useMessageThread } from '@/components/instructor/messages/hooks/useMessageThread';
import type { ConversationEntry } from '@/components/instructor/messages/types';
import type { ConversationMessage, ConversationMessagesResponse } from '@/types/conversation';

// Mock the API services
const mockUseConversationMessages = jest.fn();
const mockMarkMessagesAsReadImperative = jest.fn();

jest.mock('@/src/api/services/messages', () => ({
  useConversationMessages: (...args: unknown[]) => mockUseConversationMessages(...args),
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

const scheduleMicrotask =
  typeof queueMicrotask === 'function'
    ? queueMicrotask
    : (callback: () => void) => {
        Promise.resolve().then(callback);
      };

const triggerSuccess = (
  options: { onSuccess?: (data: ConversationMessagesResponse) => void } | undefined,
  data: ConversationMessagesResponse | undefined
) => {
  if (!options?.onSuccess || !data) return;
  scheduleMicrotask(() => {
    options.onSuccess?.(data);
  });
};

const buildMessage = (
  overrides: Partial<ConversationMessage> = {}
): ConversationMessage => ({
  id: 'msg1',
  conversation_id: 'conv1',
  content: 'Hello',
  sender_id: 'student1',
  is_from_me: false,
  message_type: 'user',
  created_at: '2024-01-01T12:00:00Z',
  is_deleted: false,
  read_by: [],
  reactions: [],
  ...overrides,
});

const buildResponse = (messages: ConversationMessage[]): ConversationMessagesResponse => ({
  messages,
  has_more: false,
});

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

    mockUseConversationMessages.mockImplementation(
      (
        conversationId: string,
        _limit?: number,
        _before?: string,
        _enabled?: boolean,
        options?: { onSuccess?: (data: ConversationMessagesResponse) => void }
      ) => {
        if (!conversationId) {
          return { data: undefined, isLoading: false, error: undefined };
        }
        const data = buildResponse([
          buildMessage({
            booking_id: 'booking1',
          }),
        ]);
        triggerSuccess(options, data);
        return {
          data,
          isLoading: false,
          error: undefined,
        };
      }
    );

    mockMarkMessagesAsReadImperative.mockResolvedValue({});
  });

  describe('conversation switching', () => {
    it('loads history for the selected conversation and switches cleanly', async () => {
      mockUseConversationMessages.mockImplementation(
        (
          conversationId: string,
          _limit?: number,
          _before?: string,
          _enabled?: boolean,
          options?: { onSuccess?: (data: ConversationMessagesResponse) => void }
        ) => {
          if (!conversationId) return { data: undefined, isLoading: false, error: undefined };
          if (conversationId === 'conv1') {
            const data = buildResponse([
              buildMessage({
                conversation_id: 'conv1',
                content: 'Hello from conv1',
                sender_id: 'student1',
                booking_id: 'booking1',
              }),
            ]);
            triggerSuccess(options, data);
            return {
              data,
              isLoading: false,
              error: undefined,
            };
          }
          const data = buildResponse([
            buildMessage({
              id: 'msg2',
              conversation_id: 'conv2',
              content: 'Hello from conv2',
              sender_id: 'student2',
              booking_id: 'booking2',
            }),
          ]);
          triggerSuccess(options, data);
          return {
            data,
            isLoading: false,
            error: undefined,
          };
        }
      );

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

      const callsForConv1 = mockUseConversationMessages.mock.calls.filter((call) => call[0] === 'conv1');
      const callsForConv2 = mockUseConversationMessages.mock.calls.filter((call) => call[0] === 'conv2');
      expect(callsForConv1.length).toBeGreaterThan(0);
      expect(callsForConv2.length).toBeGreaterThan(0);
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
          mockUseConversationMessages.mock.calls.some(
            (call) => call[0] === 'conv1' && call[3] === true
          )
        ).toBe(true);
      });

      const callsBefore = mockUseConversationMessages.mock.calls.length;

      // Invalidate and reload
      await act(async () => {
        result.current.invalidateConversationCache('conv1');
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(mockUseConversationMessages.mock.calls.length).toBeGreaterThan(callsBefore);
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
      mockUseConversationMessages.mockImplementation(
        (
          _conversationId: string,
          _limit?: number,
          _before?: string,
          _enabled?: boolean,
          options?: { onSuccess?: (data: ConversationMessagesResponse) => void }
        ) => {
          const data = buildResponse([
            buildMessage({
              content: 'Unread message',
              sender_id: 'student1', // From student, not current user
              booking_id: 'booking1',
              read_by: [], // Not read by current user
            }),
          ]);
          triggerSuccess(options, data);
          return {
            data,
            isLoading: false,
            error: undefined,
          };
        }
      );

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

      const callCountBefore = mockUseConversationMessages.mock.calls.length;

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      expect(mockUseConversationMessages.mock.calls.length).toBeLessThanOrEqual(callCountBefore + 1);
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

      mockUseConversationMessages.mockClear();
      rerender({ convos: [newerConversation] });

      await act(async () => {
        result.current.loadThreadMessages('conv1', newerConversation, 'inbox');
      });

      expect(
        mockUseConversationMessages.mock.calls.some(
          (call) => call[0] === 'conv1' && call[3] === true
        )
      ).toBe(true);
    });
  });
});
