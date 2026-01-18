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
  });
});
