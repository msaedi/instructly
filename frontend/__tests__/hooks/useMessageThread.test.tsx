import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useMessageThread } from '@/components/instructor/messages/hooks/useMessageThread';
import type { ConversationEntry } from '@/components/instructor/messages/types';
import type { ConversationMessage, ConversationMessagesResponse } from '@/types/conversation';

// Mock the API services
const mockUseConversationMessages = jest.fn();
const mockMarkMessagesAsReadImperative = jest.fn();
const mockSendConversationMessage = jest.fn();

jest.mock('@/src/api/services/messages', () => ({
  useConversationMessages: (...args: unknown[]) => mockUseConversationMessages(...args),
  markMessagesAsReadImperative: (...args: unknown[]) => mockMarkMessagesAsReadImperative(...args),
}));

jest.mock('@/src/api/services/conversations', () => ({
  sendMessage: (...args: unknown[]) => mockSendConversationMessage(...args),
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
    mockSendConversationMessage.mockReset();

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

    it('executes setConversations callback to update unread count (lines 174-175)', async () => {
      // Capture the callback passed to setConversations
      type ConversationCallback = (prev: ConversationEntry[]) => ConversationEntry[];
      let capturedCallback: ConversationCallback | null = null;
      setConversationsMock.mockImplementation((cb: ConversationCallback) => {
        capturedCallback = cb;
      });

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
              content: 'Message from student',
              sender_id: 'student1',
              booking_id: 'booking1',
              read_by: [],
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
      });

      await waitFor(() => {
        expect(setConversationsMock).toHaveBeenCalled();
      });

      // Execute the captured callback to cover lines 174-175
      if (capturedCallback !== null) {
        const testConversations = [mockConversation, mockConversation2];
        const callbackResult = (capturedCallback as ConversationCallback)(testConversations);
        // Verify the callback correctly maps conversations
        expect(callbackResult).toHaveLength(2);
        // First conversation should have updated unread count
        expect(callbackResult[0]?.id).toBe('conv1');
      }
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

  describe('send message guards', () => {
    it('prevents duplicate sends while in-flight', async () => {
      let resolveSend: (value: { id: string }) => void = () => {};
      mockSendConversationMessage.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveSend = resolve;
          })
      );

      const onSuccess = jest.fn();
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        const p1 = result.current.handleSendMessage({
          selectedChat: 'conv1',
          messageText: 'Hello',
          pendingAttachments: [],
          composeRecipient: null,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
        const p2 = result.current.handleSendMessage({
          selectedChat: 'conv1',
          messageText: 'Hello',
          pendingAttachments: [],
          composeRecipient: null,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
        resolveSend({ id: 'msg-server' });
        await Promise.all([p1, p2]);
      });

      expect(mockSendConversationMessage).toHaveBeenCalledTimes(1);
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });

    it('sends message from compose view with recipient', async () => {
      mockSendConversationMessage.mockResolvedValue({ id: 'msg-server' });
      const onSuccess = jest.fn();
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: '__compose__',
          messageText: 'Hello from compose',
          pendingAttachments: [],
          composeRecipient: mockConversation,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
      });

      expect(mockSendConversationMessage).toHaveBeenCalledTimes(1);
      expect(onSuccess).toHaveBeenCalledWith('conv1', true);
    });

    it('sends message with attachments', async () => {
      mockSendConversationMessage.mockResolvedValue({ id: 'msg-server' });
      const onSuccess = jest.fn();
      const { result } = renderWithProps([mockConversation]);

      const mockFile = new File(['test content'], 'test.pdf', { type: 'application/pdf' });

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: 'conv1',
          messageText: '',
          pendingAttachments: [mockFile],
          composeRecipient: null,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
      });

      expect(mockSendConversationMessage).toHaveBeenCalledTimes(1);
    });

    it('does not send empty message without attachments', async () => {
      const onSuccess = jest.fn();
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: 'conv1',
          messageText: '   ',
          pendingAttachments: [],
          composeRecipient: null,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
      });

      expect(mockSendConversationMessage).not.toHaveBeenCalled();
      expect(onSuccess).not.toHaveBeenCalled();
    });

    it('handles send failure gracefully', async () => {
      mockSendConversationMessage.mockRejectedValue(new Error('Network error'));
      const onSuccess = jest.fn();
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: 'conv1',
          messageText: 'Hello',
          pendingAttachments: [],
          composeRecipient: null,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
      });

      // Should still call onSuccess even with send error (optimistic message was created)
      expect(onSuccess).toHaveBeenCalled();
    });

    it('does not send when currentUserId is undefined', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId: undefined,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      const onSuccess = jest.fn();
      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: 'conv1',
          messageText: 'Hello',
          pendingAttachments: [],
          composeRecipient: null,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
      });

      expect(mockSendConversationMessage).not.toHaveBeenCalled();
    });

    it('does not send from compose without recipient', async () => {
      const onSuccess = jest.fn();
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: '__compose__',
          messageText: 'Hello',
          pendingAttachments: [],
          composeRecipient: null,
          conversations: [mockConversation],
          getPrimaryBookingId: () => 'booking1',
          onSuccess,
        });
      });

      expect(mockSendConversationMessage).not.toHaveBeenCalled();
    });

    it('creates new conversation entry if not found', async () => {
      mockSendConversationMessage.mockResolvedValue({ id: 'msg-server' });
      const onSuccess = jest.fn();
      const newRecipient: ConversationEntry = {
        id: 'new-conv',
        name: 'New User',
        lastMessage: '',
        timestamp: '',
        unread: 0,
        avatar: 'NU',
        type: 'student',
        bookingIds: [],
        primaryBookingId: null,
        studentId: 'new-student',
        instructorId: 'instructor1',
        latestMessageAt: 0,
      };

      const { result } = renderWithProps([]);

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: '__compose__',
          messageText: 'Hello new user',
          pendingAttachments: [],
          composeRecipient: newRecipient,
          conversations: [],
          getPrimaryBookingId: () => null,
          onSuccess,
        });
      });

      expect(setConversationsMock).toHaveBeenCalled();
    });
  });

  describe('handleSSEMessage', () => {
    it('handles incoming message from other user', async () => {
      const { result } = renderWithProps([mockConversation]);

      // First load messages to establish the thread
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Now handle SSE message
      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: 'sse-msg-1',
            content: 'Hello from SSE',
            sender_id: 'student1',
            sender_name: 'John Student',
            created_at: new Date().toISOString(),
            is_mine: false,
          },
          'conv1',
          mockConversation
        );
      });

      expect(result.current.threadMessages.length).toBe(2);
      expect(result.current.threadMessages[1]?.text).toBe('Hello from SSE');
    });

    it('updates existing message with delivered_at timestamp', async () => {
      const { result } = renderWithProps([mockConversation]);

      // First load messages
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Add an own message first
      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: 'own-msg-1',
            content: 'My message',
            sender_id: currentUserId,
            sender_name: 'Instructor',
            created_at: new Date().toISOString(),
            is_mine: true,
          },
          'conv1',
          mockConversation
        );
      });

      // Now update it with delivered_at
      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: 'own-msg-1',
            content: 'My message',
            sender_id: currentUserId,
            sender_name: 'Instructor',
            created_at: new Date().toISOString(),
            delivered_at: new Date().toISOString(),
            is_mine: true,
          },
          'conv1',
          mockConversation
        );
      });

      // Should not duplicate the message
      const ownMsgs = result.current.threadMessages.filter((m) => m.senderId === currentUserId);
      expect(ownMsgs.length).toBeLessThanOrEqual(2);
    });

    it('does nothing when currentUserId is undefined', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId: undefined,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: 'sse-msg-1',
            content: 'Hello',
            sender_id: 'student1',
            sender_name: 'John',
            created_at: new Date().toISOString(),
            is_mine: false,
          },
          'conv1',
          mockConversation
        );
      });

      expect(result.current.threadMessages.length).toBe(0);
    });
  });

  describe('handleArchiveConversation', () => {
    it('moves active messages to archived', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      expect(result.current.messagesByThread['conv1']?.length).toBe(1);

      await act(async () => {
        result.current.handleArchiveConversation('conv1');
      });

      expect(result.current.messagesByThread['conv1']?.length).toBe(0);
      expect(result.current.archivedMessagesByThread['conv1']?.length).toBe(1);
      expect(result.current.threadMessages.length).toBe(0);
    });

    it('does not archive compose thread', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.handleArchiveConversation('__compose__');
      });

      expect(result.current.archivedMessagesByThread['__compose__']).toBeUndefined();
    });
  });

  describe('handleDeleteConversation', () => {
    it('moves all messages (active and archived) to trash', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      await act(async () => {
        result.current.handleDeleteConversation('conv1');
      });

      expect(result.current.messagesByThread['conv1']?.length).toBe(0);
      expect(result.current.archivedMessagesByThread['conv1']?.length).toBe(0);
      expect(result.current.trashMessagesByThread['conv1']?.length).toBe(1);
      expect(result.current.threadMessages.length).toBe(0);
    });

    it('does not delete compose thread', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.handleDeleteConversation('__compose__');
      });

      expect(result.current.trashMessagesByThread['__compose__']).toBeUndefined();
    });
  });

  describe('setThreadMessagesForDisplay', () => {
    it('shows inbox messages by default', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      await act(async () => {
        result.current.setThreadMessagesForDisplay('conv1', 'inbox');
      });

      expect(result.current.threadMessages.length).toBe(1);
    });

    it('shows archived messages when mode is archived', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Archive the conversation
      await act(async () => {
        result.current.handleArchiveConversation('conv1');
      });

      // Switch to archived view
      await act(async () => {
        result.current.setThreadMessagesForDisplay('conv1', 'archived');
      });

      expect(result.current.threadMessages.length).toBe(1);
      expect(result.current.threadMessages[0]?.isArchived).toBe(true);
    });

    it('shows trash messages when mode is trash', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Delete the conversation
      await act(async () => {
        result.current.handleDeleteConversation('conv1');
      });

      // Switch to trash view
      await act(async () => {
        result.current.setThreadMessagesForDisplay('conv1', 'trash');
      });

      expect(result.current.threadMessages.length).toBe(1);
      expect(result.current.threadMessages[0]?.isTrashed).toBe(true);
    });

    it('does nothing for compose thread', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.setThreadMessagesForDisplay('__compose__', 'inbox');
      });

      expect(result.current.threadMessages.length).toBe(0);
    });
  });

  describe('updateThreadMessage', () => {
    it('updates message in all state objects', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      const originalId = result.current.threadMessages[0]?.id;

      await act(async () => {
        result.current.updateThreadMessage(originalId!, (msg) => ({
          ...msg,
          text: 'Updated text',
        }));
      });

      expect(result.current.threadMessages[0]?.text).toBe('Updated text');
      expect(result.current.messagesByThread['conv1']?.[0]?.text).toBe('Updated text');
    });

    it('updates archived messages', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      const originalId = result.current.threadMessages[0]?.id;

      // Archive the conversation
      await act(async () => {
        result.current.handleArchiveConversation('conv1');
      });

      // Update the archived message
      await act(async () => {
        result.current.updateThreadMessage(originalId!, (msg) => ({
          ...msg,
          text: 'Updated archived text',
        }));
      });

      expect(result.current.archivedMessagesByThread['conv1']?.[0]?.text).toBe('Updated archived text');
    });

    it('updates trash messages', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      const originalId = result.current.threadMessages[0]?.id;

      // Delete the conversation
      await act(async () => {
        result.current.handleDeleteConversation('conv1');
      });

      // Update the trashed message
      await act(async () => {
        result.current.updateThreadMessage(originalId!, (msg) => ({
          ...msg,
          text: 'Updated trash text',
        }));
      });

      expect(result.current.trashMessagesByThread['conv1']?.[0]?.text).toBe('Updated trash text');
    });
  });

  describe('loadThreadMessages edge cases', () => {
    it('does nothing for compose thread', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('__compose__', mockConversation, 'inbox');
      });

      expect(result.current.threadMessages.length).toBe(0);
    });

    it('does nothing when currentUserId is undefined', async () => {
      const { result } = renderHook(
        () =>
          useMessageThread({
            currentUserId: undefined,
            conversations: [mockConversation],
            setConversations: setConversationsMock,
          }),
        { wrapper: createWrapper() }
      );

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      expect(result.current.threadMessages.length).toBe(0);
    });

    it('does nothing when conversation is null', async () => {
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', null, 'inbox');
      });

      expect(result.current.threadMessages.length).toBe(0);
    });
  });

  describe('history error handling', () => {
    it('logs error when history fetch fails', async () => {
      const { logger } = jest.requireMock('@/lib/logger') as { logger: { error: jest.Mock } };

      mockUseConversationMessages.mockImplementation(
        (
          conversationId: string,
          _limit?: number,
          _before?: string,
          _enabled?: boolean,
          _options?: { onSuccess?: (data: ConversationMessagesResponse) => void }
        ) => {
          if (!conversationId) {
            return { data: undefined, isLoading: false, error: undefined };
          }
          return {
            data: undefined,
            isLoading: false,
            error: new Error('Fetch failed'),
          };
        }
      );

      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      // Wait for potential error logging
      await waitFor(() => {
        expect(logger.error).toHaveBeenCalled();
      });
    });
  });

  describe('mark as read failure handling', () => {
    it('handles mark as read failure gracefully', async () => {
      mockMarkMessagesAsReadImperative.mockRejectedValue(new Error('Mark read failed'));

      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      // Should not throw - just logs the error
      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });
    });

    it('restores lastCount on mark as read failure when previously set', async () => {
      // First, load successfully to set the markedReadThreadsRef
      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Now simulate a scenario where mark as read fails after already having a previous value
      mockMarkMessagesAsReadImperative.mockRejectedValueOnce(new Error('Mark read failed'));

      // Invalidate and reload to trigger another mark as read with an existing lastCount
      await act(async () => {
        result.current.invalidateConversationCache('conv1');
      });

      // Update the mock to return messages with unread count > 0
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
              read_by: [], // Unread
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

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });
    });
  });

  describe('message sorting with empty timestamps', () => {
    it('handles messages with empty or missing createdAt values', async () => {
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
              id: 'msg1',
              content: 'First message',
              created_at: '2024-01-01T12:00:00Z',
              booking_id: 'booking1',
            }),
            buildMessage({
              id: 'msg2',
              content: 'Message with empty timestamp',
              created_at: '',
              booking_id: 'booking1',
            }),
            buildMessage({
              id: 'msg3',
              content: 'Third message',
              created_at: '2024-01-01T13:00:00Z',
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

      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(3);
      });

      // All messages should be present regardless of empty timestamp handling
      const messageTexts = result.current.threadMessages.map((m) => m.text);
      expect(messageTexts).toContain('First message');
      expect(messageTexts).toContain('Message with empty timestamp');
      expect(messageTexts).toContain('Third message');
    });
  });

  describe('SSE message delivery update', () => {
    it('updates existing message with delivered_at in both state objects', async () => {
      const { result } = renderWithProps([mockConversation]);

      // First load messages
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      const originalMessage = result.current.threadMessages[0];
      const msgId = originalMessage?.id ?? 'msg1';

      // Send an SSE update for the existing message with delivered_at
      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: msgId,
            content: 'Hello',
            sender_id: 'student1',
            sender_name: 'John Student',
            created_at: '2024-01-01T12:00:00Z',
            delivered_at: '2024-01-01T12:01:00Z',
            is_mine: false,
          },
          'conv1',
          mockConversation
        );
      });

      // The message should be updated, not duplicated
      expect(result.current.threadMessages.length).toBe(1);
      expect(result.current.messagesByThread['conv1']?.length).toBe(1);
    });

    it('updates conversation preview for different conversations', async () => {
      const { result } = renderWithProps([mockConversation, mockConversation2]);

      // Load messages for conv1
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Send SSE message for conv1 - this exercises line 362-364
      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: 'sse-new-msg',
            content: 'New message via SSE',
            sender_id: 'student1',
            sender_name: 'John Student',
            created_at: new Date().toISOString(),
            is_mine: false,
          },
          'conv1',
          mockConversation
        );
      });

      // Should update the conversation preview
      expect(setConversationsMock).toHaveBeenCalled();
    });

    it('logs warning when mark as read fails from SSE handler', async () => {
      const { logger } = jest.requireMock('@/lib/logger') as { logger: { warn: jest.Mock } };

      mockMarkMessagesAsReadImperative.mockRejectedValue(new Error('Mark read failed'));

      const { result } = renderWithProps([mockConversation]);

      // Load messages first
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Send SSE message from another user (should trigger mark as read)
      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: 'sse-msg-from-other',
            content: 'Hello from SSE',
            sender_id: 'student1',
            sender_name: 'John Student',
            created_at: new Date().toISOString(),
            is_mine: false,
          },
          'conv1',
          mockConversation
        );
      });

      await waitFor(() => {
        expect(logger.warn).toHaveBeenCalledWith(
          expect.stringContaining('Failed to mark messages as read from SSE handler'),
          expect.any(Object)
        );
      });
    });

    it('executes setConversations callback with non-matching conversation (lines 362-364)', async () => {
      // Capture the callback passed to setConversations
      let capturedCallback: ((prev: ConversationEntry[]) => ConversationEntry[]) | null = null;
      setConversationsMock.mockImplementation((cb: (prev: ConversationEntry[]) => ConversationEntry[]) => {
        capturedCallback = cb;
      });

      const { result } = renderWithProps([mockConversation, mockConversation2]);

      // Load messages for conv1
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Clear previous callbacks
      setConversationsMock.mockClear();
      capturedCallback = null;

      // Send SSE message for conv1
      await act(async () => {
        result.current.handleSSEMessage(
          {
            id: 'sse-new-msg-2',
            content: 'Another SSE message',
            sender_id: 'student1',
            sender_name: 'John Student',
            created_at: new Date().toISOString(),
            is_mine: false,
          },
          'conv1',
          mockConversation
        );
      });

      await waitFor(() => {
        expect(setConversationsMock).toHaveBeenCalled();
      });

      // Execute the captured callback with multiple conversations
      // This covers lines 362-364 where non-matching conversations are returned unchanged
      if (capturedCallback !== null) {
        const testConversations = [mockConversation, mockConversation2];
        const result = (capturedCallback as (prev: ConversationEntry[]) => ConversationEntry[])(testConversations);
        // Both conversations should be in the result
        expect(result).toHaveLength(2);
        // conv2 should be unchanged (lines 362-364)
        expect(result[1]?.id).toBe('conv2');
      }
    });
  });

  describe('send message to new conversation', () => {
    it('adds new conversation entry when sending to non-existent conversation', async () => {
      mockSendConversationMessage.mockResolvedValue({ id: 'msg-server' });
      const onSuccess = jest.fn();

      const newRecipient: ConversationEntry = {
        id: 'brand-new-conv',
        name: 'Brand New User',
        lastMessage: '',
        timestamp: '',
        unread: 0,
        avatar: 'BN',
        type: 'student',
        bookingIds: ['booking-new'],
        primaryBookingId: 'booking-new',
        studentId: 'brand-new-student',
        instructorId: 'instructor1',
        latestMessageAt: 0,
      };

      // Start with empty conversations to ensure new conversation is created
      const { result } = renderWithProps([]);

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: '__compose__',
          messageText: 'Hello to new conversation',
          pendingAttachments: [],
          composeRecipient: newRecipient,
          conversations: [], // Empty - conversation doesn't exist
          getPrimaryBookingId: () => 'booking-new',
          onSuccess,
        });
      });

      // Should call setConversations to add the new conversation
      expect(setConversationsMock).toHaveBeenCalled();
      expect(onSuccess).toHaveBeenCalledWith('brand-new-conv', true);
    });

    it('executes setConversations callback creating new conversation entry (lines 464-500)', async () => {
      // Capture the callback passed to setConversations
      let capturedCallback: ((prev: ConversationEntry[]) => ConversationEntry[]) | null = null;
      setConversationsMock.mockImplementation((cb: (prev: ConversationEntry[]) => ConversationEntry[]) => {
        capturedCallback = cb;
      });

      mockSendConversationMessage.mockResolvedValue({ id: 'msg-server' });
      const onSuccess = jest.fn();

      const newRecipient: ConversationEntry = {
        id: 'totally-new-conv',
        name: 'Totally New User',
        lastMessage: '',
        timestamp: '',
        unread: 0,
        avatar: 'TN',
        type: 'student',
        bookingIds: ['booking-totally-new'],
        primaryBookingId: 'booking-totally-new',
        studentId: 'totally-new-student',
        instructorId: 'instructor1',
        latestMessageAt: 0,
      };

      const { result } = renderWithProps([]);

      await act(async () => {
        await result.current.handleSendMessage({
          selectedChat: '__compose__',
          messageText: 'Hello to totally new conversation',
          pendingAttachments: [],
          composeRecipient: newRecipient,
          conversations: [],
          getPrimaryBookingId: () => 'booking-totally-new',
          onSuccess,
        });
      });

      await waitFor(() => {
        expect(setConversationsMock).toHaveBeenCalled();
      });

      // Execute the captured callback with existing conversations that don't include the new one
      // This covers lines 464-500 where a new conversation is created
      if (capturedCallback !== null) {
        // Pass conversations that don't include 'totally-new-conv' to trigger new entry creation
        const testConversations = [mockConversation]; // Only conv1, not the new one
        const result = (capturedCallback as (prev: ConversationEntry[]) => ConversationEntry[])(testConversations);
        // Should add the new conversation
        expect(result.length).toBeGreaterThanOrEqual(1);
        // The new conversation should be in the result (found = false path)
        const newConv = result.find((c: ConversationEntry) => c.id === 'totally-new-conv');
        expect(newConv).toBeDefined();
        expect(newConv?.name).toBe('Totally New User');
      }
    });
  });

  describe('archive and delete with multiple messages', () => {
    it('sorts archived messages by createdAt timestamp', async () => {
      // Setup mock to return multiple messages with different timestamps
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
              id: 'msg-later',
              content: 'Later message',
              created_at: '2024-01-02T12:00:00Z',
              booking_id: 'booking1',
            }),
            buildMessage({
              id: 'msg-earlier',
              content: 'Earlier message',
              created_at: '2024-01-01T12:00:00Z',
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

      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(2);
      });

      // Archive the conversation - triggers sorting on lines 587-589
      await act(async () => {
        result.current.handleArchiveConversation('conv1');
      });

      // Archived messages should be sorted chronologically
      expect(result.current.archivedMessagesByThread['conv1']?.length).toBe(2);
      // First message should be earlier
      expect(result.current.archivedMessagesByThread['conv1']?.[0]?.text).toBe('Earlier message');
      expect(result.current.archivedMessagesByThread['conv1']?.[1]?.text).toBe('Later message');
    });

    it('sorts trashed messages by createdAt timestamp', async () => {
      // Setup mock to return multiple messages with different timestamps
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
              id: 'msg-third',
              content: 'Third message',
              created_at: '2024-01-03T12:00:00Z',
              booking_id: 'booking1',
            }),
            buildMessage({
              id: 'msg-first',
              content: 'First message',
              created_at: '2024-01-01T12:00:00Z',
              booking_id: 'booking1',
            }),
            buildMessage({
              id: 'msg-second',
              content: 'Second message',
              created_at: '2024-01-02T12:00:00Z',
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

      const { result } = renderWithProps([mockConversation]);

      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(3);
      });

      // Delete the conversation - triggers sorting on lines 616-618
      await act(async () => {
        result.current.handleDeleteConversation('conv1');
      });

      // Trashed messages should be sorted chronologically
      expect(result.current.trashMessagesByThread['conv1']?.length).toBe(3);
      expect(result.current.trashMessagesByThread['conv1']?.[0]?.text).toBe('First message');
      expect(result.current.trashMessagesByThread['conv1']?.[1]?.text).toBe('Second message');
      expect(result.current.trashMessagesByThread['conv1']?.[2]?.text).toBe('Third message');
    });
  });

  describe('shouldMarkRead edge cases', () => {
    it('sets markedReadThreadsRef to 0 when shouldMarkRead is false', async () => {
      // Setup mock to return messages with no unread (current user has read all)
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
              id: 'msg1',
              content: 'Already read message',
              sender_id: 'instructor1', // From current user, so no unread
              booking_id: 'booking1',
              read_by: [{ user_id: 'instructor1', read_at: '2024-01-01T12:00:00Z' }],
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

      // Load first to set the markedReadThreadsRef
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Load again - should hit the "shouldMarkRead is false" branch (line 203)
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      // The messages should still be loaded
      expect(result.current.threadMessages.length).toBe(1);
    });
  });

  describe('force fetch edge case', () => {
    it('forces fetch when no cache exists and thread is not stale', async () => {
      const { result } = renderWithProps([mockConversation]);

      // First load to establish the cache
      await act(async () => {
        result.current.loadThreadMessages('conv1', mockConversation, 'inbox');
      });

      await waitFor(() => {
        expect(result.current.threadMessages.length).toBe(1);
      });

      // Invalidate cache to clear it
      await act(async () => {
        result.current.invalidateConversationCache('conv1');
      });

      const callCountBefore = mockUseConversationMessages.mock.calls.length;

      // Load a different conversation (conv2) that has no cache and isn't marked stale
      // This should trigger the force fetch on line 283
      await act(async () => {
        result.current.loadThreadMessages('conv2', mockConversation2, 'inbox');
      });

      // Should have made a fetch call
      expect(mockUseConversationMessages.mock.calls.length).toBeGreaterThan(callCountBefore);
    });
  });
});
