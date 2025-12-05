import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { Chat } from '../Chat';
import type { MessageResponse } from '@/src/api/generated/instructly.schemas';

const mockUseMessageHistory = jest.fn();
const mockUseSendMessage = jest.fn();
const mockUseMarkMessagesAsRead = jest.fn();
const mockUseEditMessage = jest.fn();
const mockUseDeleteMessage = jest.fn();
const mockUseAddReaction = jest.fn();
const mockUseRemoveReaction = jest.fn();
const mockUseSendTypingIndicator = jest.fn();
const mockUseMessageStream = jest.fn();

// Mock react-query hooks used by Chat component
jest.mock('@tanstack/react-query', () => ({
  ...jest.requireActual('@tanstack/react-query'),
  useQueryClient: () => ({
    invalidateQueries: jest.fn(),
  }),
  // Phase 7: Chat.tsx now uses useQuery to fetch conversation_id
  useQuery: () => ({
    data: { id: 'conversation-123', created: false },
    isLoading: false,
    error: null,
  }),
}));

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
  useMessageHistory: (...args: unknown[]) => mockUseMessageHistory(...args),
  useSendMessage: (...args: unknown[]) => mockUseSendMessage(...args),
  useMarkMessagesAsRead: (...args: unknown[]) => mockUseMarkMessagesAsRead(...args),
  useEditMessage: (...args: unknown[]) => mockUseEditMessage(...args),
  useDeleteMessage: (...args: unknown[]) => mockUseDeleteMessage(...args),
  useAddReaction: (...args: unknown[]) => mockUseAddReaction(...args),
  useRemoveReaction: (...args: unknown[]) => mockUseRemoveReaction(...args),
  useSendTypingIndicator: (...args: unknown[]) => mockUseSendTypingIndicator(...args),
}));

// Mock queryKeys
jest.mock('@/src/api/queryKeys', () => ({
  queryKeys: {
    messages: {
      config: ['messages', 'config'],
      unreadCount: ['messages', 'unread-count'],
      history: (bookingId: string) => ['messages', 'history', bookingId, {}],
    },
  },
}));

const baseProps = {
  bookingId: 'booking-123',
  currentUserId: 'user-1',
  currentUserName: 'Instructor A',
  otherUserName: 'Student A',
};

const defaultHistoryResponse = (messages: MessageResponse[] = []) => ({
  data: {
    booking_id: baseProps.bookingId,
    messages,
    limit: messages.length,
    offset: 0,
    has_more: false,
  },
  isLoading: false,
  error: null,
});

const buildMessage = (id: string, overrides: Partial<MessageResponse> = {}): MessageResponse => ({
  id,
  booking_id: baseProps.bookingId,
  sender_id: overrides.sender_id ?? 'student-1',
  content: overrides.content ?? 'Hello!',
  created_at: overrides.created_at ?? new Date('2024-01-01T00:00:00Z').toISOString(),
  updated_at: overrides.updated_at ?? new Date('2024-01-01T00:00:00Z').toISOString(),
  is_deleted: overrides.is_deleted ?? false,
  read_by: overrides.read_by,
  delivered_at: overrides.delivered_at,
  edited_at: overrides.edited_at,
  sender: overrides.sender,
});

beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

describe('Chat mark-as-read behavior', () => {
  let markMessagesAsReadMutate: jest.Mock;
  let historyResponse: ReturnType<typeof defaultHistoryResponse>;

  beforeEach(() => {
    jest.clearAllMocks();

    mockUseSendMessage.mockReturnValue({ mutateAsync: jest.fn(), isPending: false });
    markMessagesAsReadMutate = jest.fn();
    mockUseMarkMessagesAsRead.mockImplementation(() => ({ mutate: markMessagesAsReadMutate }));
    mockUseEditMessage.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseDeleteMessage.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseAddReaction.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseRemoveReaction.mockReturnValue({ mutateAsync: jest.fn() });
    mockUseSendTypingIndicator.mockReturnValue({ mutate: jest.fn() });
    mockUseMessageStream.mockReturnValue({
      isConnected: true,
      connectionError: null,
      subscribe: jest.fn(() => jest.fn()), // Returns unsubscribe function
    });

    historyResponse = defaultHistoryResponse();
    mockUseMessageHistory.mockImplementation(() => historyResponse);
  });

  const setHistoryMessages = (messages: MessageResponse[]) => {
    historyResponse = defaultHistoryResponse(messages);
  };

  it('does not call mark-read when every message is already read', async () => {
    const readMessage = buildMessage('msg-read', {
      read_by: [{ user_id: baseProps.currentUserId, read_at: new Date('2024-01-01T02:00:00Z').toISOString() }],
    });
    setHistoryMessages([readMessage]);

    render(<Chat {...baseProps} />);

    await waitFor(() => expect(markMessagesAsReadMutate).not.toHaveBeenCalled());
  });

  it('only marks unread messages once even if the component re-renders', async () => {
    const unreadMessage = buildMessage('msg-unread', { read_by: [] });
    setHistoryMessages([unreadMessage]);

    const { rerender } = render(<Chat {...baseProps} />);

    await waitFor(() => expect(markMessagesAsReadMutate).toHaveBeenCalledTimes(1));

    rerender(<Chat {...baseProps} otherUserName="Student B" />);

    await waitFor(() => expect(markMessagesAsReadMutate).toHaveBeenCalledTimes(1));
  });

  it('marks messages again when a newer unread message appears', async () => {
    setHistoryMessages([buildMessage('msg-one', { read_by: [] })]);

    const { rerender } = render(<Chat {...baseProps} />);

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

    rerender(<Chat {...baseProps} />);

    await waitFor(() => expect(markMessagesAsReadMutate).toHaveBeenCalledTimes(2));
  });
});
