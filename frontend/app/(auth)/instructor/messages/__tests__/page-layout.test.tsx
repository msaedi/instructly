/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import MessagesPage from '../page';
import { EmbeddedContext } from '../../_embedded/EmbeddedContext';

const mockUseSearchParams = jest.fn();
const mockReplace = jest.fn();
const mockUseAuthStatus = jest.fn();
const mockSubscribe = jest.fn(() => jest.fn());
const mockUseConversations = jest.fn();

function MockUserProfileDropdown() {
  return <div>User menu</div>;
}

jest.mock('@/components/UserProfileDropdown', () => MockUserProfileDropdown);

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

jest.mock('@/components/instructor/messages/hooks', () => ({
  useConversations: (...args: unknown[]) => mockUseConversations(...args),
  useUpdateConversationState: () => ({ mutate: jest.fn() }),
  useMessageDrafts: () => ({
    draftsByThread: {},
    updateDraft: jest.fn(),
    clearDraft: jest.fn(),
    getDraftKey: (threadId: string | null) => threadId ?? 'draft',
  }),
  useMessageThread: () => ({
    threadMessages: [],
    archivedMessagesByThread: {},
    trashMessagesByThread: {},
    loadThreadMessages: jest.fn(),
    handleSSEMessage: jest.fn(),
    handleSendMessage: jest.fn(),
    setThreadMessagesForDisplay: jest.fn(),
    updateThreadMessage: jest.fn(),
    invalidateConversationCache: jest.fn(),
  }),
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
}));

jest.mock('@/components/instructor/messages/components', () => ({
  ChatHeader: () => <div>Chat header</div>,
  ConversationList: () => <div>Conversation list</div>,
  MessageInput: () => <div>Message input</div>,
  TemplateEditor: () => <div>Template editor</div>,
}));

jest.mock('@/components/messaging', () => ({
  MessageBubble: () => <div>Message bubble</div>,
  normalizeInstructorMessage: jest.fn(),
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

describe('MessagesPage layout', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockUseSearchParams.mockReturnValue({
      get: (key: string) => (key === 'conversation' ? null : null),
      toString: () => '',
    });

    mockUseAuthStatus.mockReturnValue({
      user: { id: 'instructor-1' },
      isLoading: false,
    });

    mockUseConversations.mockReturnValue({
      conversations: [
        {
          id: 'conversation-1',
          name: 'Emma Johnson',
          lastMessage: 'See you soon',
          timestamp: 'Today',
          unread: 1,
          avatar: '',
          type: 'student',
          bookingIds: ['booking-1'],
          primaryBookingId: 'booking-1',
          studentId: 'student-1',
          instructorId: 'instructor-1',
          latestMessageAt: Date.now(),
          latestMessageId: 'message-1',
          upcomingBookingCount: 1,
        },
      ],
      setConversations: jest.fn(),
      isLoading: false,
      error: null,
    });
  });

  it('redirects the standalone route to the dashboard messages panel', () => {
    mockUseSearchParams.mockReturnValue({
      get: (key: string) => (key === 'conversation' ? 'conversation-1' : null),
      toString: () => 'conversation=conversation-1',
    });

    render(<MessagesPage />);

    expect(mockReplace).toHaveBeenCalledWith(
      '/instructor/dashboard?conversation=conversation-1&panel=messages',
      {
        scroll: false,
      }
    );
  });

  it('renders the messages UI when embedded inside the dashboard', () => {
    render(
      <EmbeddedContext.Provider value={true}>
        <MessagesPage />
      </EmbeddedContext.Provider>
    );

    expect(screen.getByRole('heading', { name: 'Messages' })).toBeInTheDocument();
    expect(screen.getByText('Conversation list')).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('shows the hidden section copy and toggles to templates view', () => {
    render(
      <EmbeddedContext.Provider value={true}>
        <MessagesPage />
      </EmbeddedContext.Provider>
    );

    const switcher = screen.getByTestId('messages-section-switcher');
    expect(within(switcher).getByRole('heading', { name: 'Communication templates' })).toBeInTheDocument();
    expect(within(switcher).getByText('Access saved templates for quick replies.')).toBeInTheDocument();

    fireEvent.click(within(switcher).getByRole('button'));

    expect(within(switcher).getByRole('heading', { name: 'Messages' })).toBeInTheDocument();
    expect(within(switcher).getByText('Stay in touch with everyone.')).toBeInTheDocument();
    expect(screen.getByText('Template editor')).toBeInTheDocument();
  });

  it('uses the reduced whitespace inbox shell classes', () => {
    render(
      <EmbeddedContext.Provider value={true}>
        <MessagesPage />
      </EmbeddedContext.Provider>
    );

    const inboxShell = screen.getByTestId('messages-inbox-shell');
    expect(inboxShell).toHaveClass('min-h-0', 'flex-1');
    expect(inboxShell).not.toHaveClass('min-h-[680px]');
  });
});
