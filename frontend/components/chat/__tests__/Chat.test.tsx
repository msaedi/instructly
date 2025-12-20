import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Chat } from '../Chat';
import type { ConversationMessage } from '@/types/conversation';

const mockUseConversationMessages = jest.fn();
const mockUseMarkMessagesAsRead = jest.fn();
const mockUseEditMessage = jest.fn();
const mockUseDeleteMessage = jest.fn();
const mockUseAddReaction = jest.fn();
const mockUseRemoveReaction = jest.fn();
const mockUseSendConversationMessage = jest.fn();
const mockUseSendConversationTyping = jest.fn();
const mockUseMessageStream = jest.fn();

// Mock UserMessageStreamProvider (Phase 4: per-user SSE)
jest.mock('@/providers/UserMessageStreamProvider', () => ({
  useMessageStream: (...args: unknown[]) => mockUseMessageStream(...args),
}));

// Mock all message services from Orval layer
jest.mock('@/src/api/services/messages', () => ({
  useMessageConfig: () => ({
    data: { edit_window_minutes: 5 },
    isLoading: false,
    error: null,
  }),
  useConversationMessages: (...args: unknown[]) => mockUseConversationMessages(...args),
  useMarkMessagesAsRead: (...args: unknown[]) => mockUseMarkMessagesAsRead(...args),
  useEditMessage: (...args: unknown[]) => mockUseEditMessage(...args),
  useDeleteMessage: (...args: unknown[]) => mockUseDeleteMessage(...args),
  useAddReaction: (...args: unknown[]) => mockUseAddReaction(...args),
  useRemoveReaction: (...args: unknown[]) => mockUseRemoveReaction(...args),
}));

jest.mock('@/src/api/services/conversations', () => ({
  useSendConversationMessage: (...args: unknown[]) => mockUseSendConversationMessage(...args),
  useSendConversationTyping: (...args: unknown[]) => mockUseSendConversationTyping(...args),
}));

// Mock queryKeys
jest.mock('@/src/api/queryKeys', () => ({
  queryKeys: {
    messages: {
      config: ['messages', 'config'],
      unreadCount: ['messages', 'unread-count'],
      conversationMessages: (conversationId: string) => ['messages', 'conversation', conversationId, {}],
    },
  },
}));

const baseProps = {
  conversationId: 'conversation-123',
  bookingId: 'booking-123',
  currentUserId: 'user-1',
  currentUserName: 'Instructor A',
  otherUserName: 'Student A',
};

const defaultHistoryResponse = (messages: ConversationMessage[] = []) => ({
  data: {
    messages,
    has_more: false,
    next_cursor: null,
  },
  isLoading: false,
  error: null,
});

const buildMessage = (id: string, overrides: Partial<ConversationMessage> = {}): ConversationMessage => ({
  id,
  conversation_id: baseProps.conversationId,
  content: overrides.content ?? 'Hello!',
  sender_id: overrides.sender_id ?? 'student-1',
  is_from_me: overrides.is_from_me ?? false,
  message_type: overrides.message_type ?? 'user',
  booking_id: overrides.booking_id ?? baseProps.bookingId,
  booking_details: overrides.booking_details ?? null,
  created_at: overrides.created_at ?? new Date('2024-01-01T00:00:00Z').toISOString(),
  edited_at: overrides.edited_at ?? null,
  is_deleted: overrides.is_deleted ?? false,
  delivered_at: overrides.delivered_at ?? null,
  read_by: overrides.read_by ?? [],
  reactions: overrides.reactions ?? [],
});

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

describe('Chat mark-as-read behavior', () => {
  let markMessagesAsReadMutate: jest.Mock;
  let historyResponse: ReturnType<typeof defaultHistoryResponse>;
  let queryClient: QueryClient;

  beforeEach(() => {
    jest.clearAllMocks();
    queryClient = new QueryClient();

    mockUseSendConversationMessage.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    mockUseSendConversationTyping.mockReturnValue({ mutate: jest.fn() });
    markMessagesAsReadMutate = jest.fn();
    mockUseMarkMessagesAsRead.mockImplementation(() => ({ mutate: markMessagesAsReadMutate }));
    mockUseEditMessage.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseDeleteMessage.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseAddReaction.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseRemoveReaction.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseMessageStream.mockReturnValue({
      isConnected: true,
      connectionError: null,
      subscribe: jest.fn(() => jest.fn()), // Returns unsubscribe function
    });

    historyResponse = defaultHistoryResponse();
    mockUseConversationMessages.mockImplementation(() => historyResponse);
  });

  const setHistoryMessages = (messages: ConversationMessage[]) => {
    historyResponse = defaultHistoryResponse(messages);
  };

  it('does not call mark-read when every message is already read', async () => {
    const readMessage = buildMessage('msg-read', {
      read_by: [{ user_id: baseProps.currentUserId, read_at: new Date('2024-01-01T02:00:00Z').toISOString() }],
    });
    setHistoryMessages([readMessage]);

    render(
      <QueryClientProvider client={queryClient}>
        <Chat {...baseProps} />
      </QueryClientProvider>
    );

    await waitFor(() => expect(markMessagesAsReadMutate).not.toHaveBeenCalled());
  });

  it('only marks unread messages once even if the component re-renders', async () => {
    const unreadMessage = buildMessage('msg-unread', { read_by: [] });
    setHistoryMessages([unreadMessage]);

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <Chat {...baseProps} />
      </QueryClientProvider>
    );

    await waitFor(() => expect(markMessagesAsReadMutate).toHaveBeenCalledTimes(1));

    rerender(
      <QueryClientProvider client={queryClient}>
        <Chat {...baseProps} otherUserName="Student B" />
      </QueryClientProvider>
    );

    await waitFor(() => expect(markMessagesAsReadMutate).toHaveBeenCalledTimes(1));
  });

  it('marks messages again when a newer unread message appears', async () => {
    setHistoryMessages([buildMessage('msg-one', { read_by: [] })]);

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <Chat {...baseProps} />
      </QueryClientProvider>
    );

    await waitFor(() => expect(markMessagesAsReadMutate).toHaveBeenCalledTimes(1));

    setHistoryMessages([
      buildMessage('msg-one', {
        read_by: [{ user_id: baseProps.currentUserId, read_at: new Date('2024-01-01T02:00:00Z').toISOString() }],
        created_at: new Date('2024-01-01T00:00:00Z').toISOString(),
      }),
      buildMessage('msg-two', {
        read_by: [],
        created_at: new Date('2024-01-01T03:00:00Z').toISOString(),
      }),
    ]);

    rerender(
      <QueryClientProvider client={queryClient}>
        <Chat {...baseProps} />
      </QueryClientProvider>
    );

    await waitFor(() => expect(markMessagesAsReadMutate).toHaveBeenCalledTimes(2));
  });
});
