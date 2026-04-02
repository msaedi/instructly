/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import MessagesPage from '../page';
import { EmbeddedContext } from '../../_embedded/EmbeddedContext';

const mockUseSearchParams = jest.fn();
const mockReplace = jest.fn();
const mockUseAuthStatus = jest.fn();
const mockSubscribe = jest.fn(() => jest.fn());

const mockConversationsData = [
  {
    id: 'conversation-1',
    name: 'John Doe',
    lastMessage: 'Last message from John',
    timestamp: 'Today',
    unread: 0,
    avatar: 'JD',
    type: 'student' as const,
    bookingIds: ['booking-1'],
    primaryBookingId: 'booking-1',
    studentId: 'student-1',
    instructorId: 'instructor-1',
    latestMessageAt: Date.now(),
    latestMessageId: 'message-1',
    upcomingBookingCount: 1,
  },
  {
    id: 'conversation-2',
    name: 'Emma Johnson',
    lastMessage: 'Last message from Emma',
    timestamp: 'Today',
    unread: 0,
    avatar: 'EJ',
    type: 'student' as const,
    bookingIds: ['booking-2'],
    primaryBookingId: 'booking-2',
    studentId: 'student-2',
    instructorId: 'instructor-1',
    latestMessageAt: Date.now() - 1000,
    latestMessageId: 'message-2',
    upcomingBookingCount: 1,
  },
];

jest.mock('next/navigation', () => ({
  useSearchParams: () => mockUseSearchParams(),
  useRouter: () => ({ replace: mockReplace }),
}));

jest.mock('@/hooks/queries/useAuth', () => ({
  useAuthStatus: () => mockUseAuthStatus(),
}));

jest.mock('@/providers/UserMessageStreamProvider', () => ({
  useMessageStream: () => ({ subscribe: mockSubscribe }),
}));

jest.mock('@/src/api/services/messages', () => ({
  useAddReaction: () => ({ mutateAsync: jest.fn() }),
  useRemoveReaction: () => ({ mutateAsync: jest.fn() }),
  useEditMessage: () => ({ mutateAsync: jest.fn() }),
  useDeleteMessage: () => ({ mutateAsync: jest.fn() }),
  useMessageConfig: () => ({ data: null }),
}));

jest.mock('@/src/api/services/conversations', () => ({
  sendTypingIndicator: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('@/components/instructor/messages', () => ({
  COMPOSE_THREAD_ID: '__compose__',
  deriveConversationPastBookings: jest.fn(() => []),
}));

jest.mock('@/components/instructor/messages/hooks', () => {
  const ReactModule = require('react') as typeof import('react');

  const makeThreadMessage = (
    id: string,
    text: string,
    sender: 'student' | 'instructor' = 'student',
  ) => ({
    id,
    text,
    sender,
    createdAt: '2025-01-15T10:00:00.000Z',
    senderId: sender === 'instructor' ? 'instructor-1' : 'student-1',
    isDeleted: false,
    attachments: [],
    my_reactions: [],
  });

  return {
    useConversations: () => ({
      conversations: mockConversationsData,
      setConversations: jest.fn(),
      isLoading: false,
      error: null,
    }),
    useUpdateConversationState: () => ({ mutate: jest.fn() }),
    useMessageDrafts: () => {
      const [draftsByThread, setDraftsByThread] = ReactModule.useState<Record<string, string>>({});
      const getDraftKey = ReactModule.useCallback((threadId: string | null) => threadId ?? 'draft', []);
      const updateDraft = ReactModule.useCallback((threadId: string | null, value: string) => {
        setDraftsByThread((prev) => ({ ...prev, [getDraftKey(threadId)]: value }));
      }, [getDraftKey]);
      const clearDraft = ReactModule.useCallback((threadId: string | null) => {
        setDraftsByThread((prev) => {
          const next = { ...prev };
          delete next[getDraftKey(threadId)];
          return next;
        });
      }, [getDraftKey]);

      return {
        draftsByThread,
        updateDraft,
        clearDraft,
        getDraftKey,
      };
    },
    useMessageThread: () => {
      const threadMapRef = ReactModule.useRef<Record<string, ReturnType<typeof makeThreadMessage>[]>>({
        'conversation-1': [makeThreadMessage('message-1', 'Existing conversation message')],
        'conversation-2': [],
      });
      const [threadMessages, setThreadMessages] = ReactModule.useState(
        threadMapRef.current['conversation-1'],
      );

      const syncThread = ReactModule.useCallback((threadId: string) => {
        setThreadMessages(threadMapRef.current[threadId] ?? []);
      }, []);

      const clearThreadMessages = ReactModule.useCallback(() => {
        setThreadMessages([]);
      }, []);

      const loadThreadMessages = ReactModule.useCallback((selectedChat: string) => {
        syncThread(selectedChat);
      }, [syncThread]);

      const setThreadMessagesForDisplay = ReactModule.useCallback((selectedChat: string) => {
        syncThread(selectedChat);
      }, [syncThread]);

      const handleSendMessage = ReactModule.useCallback(async ({
        selectedChat,
        messageText,
        composeRecipient,
        onSuccess,
      }: {
        selectedChat: string | null;
        messageText: string;
        composeRecipient: { id: string } | null;
        onSuccess: (targetThreadId: string, switchingFromCompose: boolean) => void;
      }) => {
        const targetThreadId =
          selectedChat === '__compose__' && composeRecipient ? composeRecipient.id : selectedChat;

        if (!targetThreadId) {
          return;
        }

        const sentMessage = makeThreadMessage('sent-message', messageText, 'instructor');
        threadMapRef.current[targetThreadId] = [sentMessage];
        setThreadMessages([sentMessage]);
        onSuccess(targetThreadId, selectedChat === '__compose__');
      }, []);

      return {
        threadMessages,
        archivedMessagesByThread: {},
        trashMessagesByThread: {},
        clearThreadMessages,
        loadThreadMessages,
        handleSSEMessage: jest.fn(),
        handleSendMessage,
        setThreadMessagesForDisplay,
        updateThreadMessage: jest.fn(),
        invalidateConversationCache: jest.fn(),
      };
    },
    useTemplates: () => ({
      templates: [],
      setTemplates: jest.fn(),
      selectedTemplateId: null,
      setSelectedTemplateId: jest.fn(),
      templateDrafts: {},
      setTemplateDrafts: jest.fn(),
      handleTemplateSubjectChange: jest.fn(),
      handleTemplateDraftChange: jest.fn(),
    }),
  };
});

jest.mock('@/components/instructor/messages/components', () => ({
  ConversationList: ({
    conversations,
    onConversationSelect,
  }: {
    conversations: Array<{ id: string; name: string }>;
    onConversationSelect: (conversationId: string) => void;
  }) => (
    <div>
      {conversations.map((conversation) => (
        <button
          key={conversation.id}
          type="button"
          onClick={() => onConversationSelect(conversation.id)}
        >
          {conversation.name}
        </button>
      ))}
    </div>
  ),
  ChatHeader: ({
    isComposeView,
    composeRecipient,
    composeRecipientQuery,
    composeSuggestions,
    onComposeRecipientQueryChange,
    onComposeRecipientSelect,
  }: {
    isComposeView: boolean;
    composeRecipient: { name: string } | null;
    composeRecipientQuery: string;
    composeSuggestions: Array<{ id: string; name: string }>;
    onComposeRecipientQueryChange: (query: string) => void;
    onComposeRecipientSelect: (conversation: { id: string; name: string }) => void;
  }) => (
    <div>
      {isComposeView ? (
        <>
          <label htmlFor="compose-recipient-search">Search contacts</label>
          <input
            id="compose-recipient-search"
            value={composeRecipientQuery}
            onChange={(event) => onComposeRecipientQueryChange(event.target.value)}
          />
          {composeRecipient ? <div>Recipient: {composeRecipient.name}</div> : null}
          {composeSuggestions.map((suggestion) => (
            <button
              key={suggestion.id}
              type="button"
              aria-label={`Select ${suggestion.name}`}
              onClick={() => onComposeRecipientSelect(suggestion)}
            >
              Select {suggestion.name}
            </button>
          ))}
        </>
      ) : (
        <div>Chat header</div>
      )}
    </div>
  ),
  MessageInput: ({
    messageText,
    isSendDisabled,
    onMessageChange,
    onSend,
  }: {
    messageText: string;
    isSendDisabled: boolean;
    onMessageChange: (value: string) => void;
    onSend: () => void;
  }) => (
    <div>
      <label htmlFor="message-input">Message input</label>
      <textarea
        id="message-input"
        value={messageText}
        onChange={(event) => onMessageChange(event.target.value)}
      />
      <button type="button" disabled={isSendDisabled} onClick={onSend}>
        Send message
      </button>
    </div>
  ),
  TemplateEditor: () => <div>Template editor</div>,
}));

jest.mock('@/components/messaging', () => ({
  MessageBubble: ({ message }: { message: { text: string } }) => <div>{message.text}</div>,
  normalizeInstructorMessage: (message: { id: string; text: string; sender: string }) => ({
    id: message.id,
    text: message.text,
    isOwn: message.sender === 'instructor',
    attachments: [],
    isDeleted: false,
    _raw: message,
  }),
  formatRelativeTimestamp: jest.fn(() => 'just now'),
  useReactions: () => ({
    userReactions: {},
    processingReaction: null,
    handleReaction: jest.fn(),
  }),
  useReadReceipts: () => ({
    mergedReadReceipts: {},
    lastReadMessageId: null,
  }),
  useLiveTimestamp: () => 100,
  useSSEHandlers: () => ({
    typingStatus: null,
    sseReadReceipts: {},
    handleSSETyping: jest.fn(),
    handleSSEReadReceipt: jest.fn(),
  }),
}));

describe('MessagesPage compose regression', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockUseSearchParams.mockReturnValue({
      get: () => null,
      toString: () => '',
    });

    mockUseAuthStatus.mockReturnValue({
      user: { id: 'instructor-1' },
      isLoading: false,
    });
  });

  it('clears stale messages in compose mode and shows the sent compose thread after sending', async () => {
    render(
      <EmbeddedContext.Provider value={true}>
        <MessagesPage />
      </EmbeddedContext.Provider>,
    );

    await waitFor(() => {
      expect(screen.getByText('Existing conversation message')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'New Message' }));

    expect(screen.getByText('Draft your message and choose who to send it to.')).toBeInTheDocument();
    expect(screen.queryByText('Existing conversation message')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search contacts'), {
      target: { value: 'Emma' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Select Emma Johnson' }));

    expect(screen.getByText('Recipient: Emma Johnson')).toBeInTheDocument();
    expect(screen.getByText('Draft your message and choose who to send it to.')).toBeInTheDocument();
    expect(screen.queryByText('Existing conversation message')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Message input'), {
      target: { value: 'Hi from compose' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => {
      expect(screen.getByText('Hi from compose')).toBeInTheDocument();
    });

    expect(screen.queryByText('Draft your message and choose who to send it to.')).not.toBeInTheDocument();
  });
});
