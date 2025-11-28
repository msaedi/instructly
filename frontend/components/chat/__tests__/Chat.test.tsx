import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { Chat } from '../Chat';
import type { Message } from '@/services/messageService';

const mockUseMessageHistory = jest.fn();
const mockUseSendMessage = jest.fn();
const mockUseMarkAsRead = jest.fn();
const mockUseSSEMessages = jest.fn();

jest.mock('@/hooks/useMessageQueries', () => ({
  useMessageHistory: (...args: unknown[]) => mockUseMessageHistory(...args),
  useSendMessage: (...args: unknown[]) => mockUseSendMessage(...args),
  useMarkAsRead: (...args: unknown[]) => mockUseMarkAsRead(...args),
}));

jest.mock('@/hooks/useSSEMessages', () => {
  const connectionStatusValues = {
    CONNECTED: 'connected',
    CONNECTING: 'connecting',
    DISCONNECTED: 'disconnected',
    RECONNECTING: 'reconnecting',
    ERROR: 'error',
  } as const;

  return {
    ConnectionStatus: connectionStatusValues,
    useSSEMessages: (...args: unknown[]) => mockUseSSEMessages(...args),
  };
});

// Mock useMessageConfig to avoid QueryClient dependency
jest.mock('@/src/api/services/messages', () => ({
  useMessageConfig: () => ({
    data: { edit_window_minutes: 5 },
    isLoading: false,
    error: null,
  }),
}));

const baseProps = {
  bookingId: 'booking-123',
  currentUserId: 'user-1',
  currentUserName: 'Instructor A',
  otherUserName: 'Student A',
};

const defaultHistoryResponse = (messages: Message[] = []) => ({
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

const buildMessage = (id: string, overrides: Partial<Message> = {}): Message => ({
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
  let markAsReadMutate: jest.Mock;
  let historyResponse: ReturnType<typeof defaultHistoryResponse>;

  beforeEach(() => {
    jest.clearAllMocks();

    mockUseSendMessage.mockReturnValue({ mutateAsync: jest.fn() });
    markAsReadMutate = jest.fn();
    mockUseMarkAsRead.mockImplementation(() => ({ mutate: markAsReadMutate }));
    mockUseSSEMessages.mockReturnValue({
      messages: [],
      connectionStatus: 'connected',
      reconnect: jest.fn(),
      disconnect: jest.fn(),
      clearMessages: jest.fn(),
      readReceipts: {},
      typingStatus: null,
      reactionDeltas: {},
    });

    historyResponse = defaultHistoryResponse();
    mockUseMessageHistory.mockImplementation(() => historyResponse);
  });

  const setHistoryMessages = (messages: Message[]) => {
    historyResponse = defaultHistoryResponse(messages);
  };

  it('does not call mark-read when every message is already read', async () => {
    const readMessage = buildMessage('msg-read', {
      read_by: [{ user_id: baseProps.currentUserId, read_at: new Date('2024-01-01T02:00:00Z').toISOString() }],
    });
    setHistoryMessages([readMessage]);

    render(<Chat {...baseProps} />);

    await waitFor(() => expect(markAsReadMutate).not.toHaveBeenCalled());
  });

  it('only marks unread messages once even if the component re-renders', async () => {
    const unreadMessage = buildMessage('msg-unread', { read_by: [] });
    setHistoryMessages([unreadMessage]);

    const { rerender } = render(<Chat {...baseProps} />);

    await waitFor(() => expect(markAsReadMutate).toHaveBeenCalledTimes(1));

    rerender(<Chat {...baseProps} otherUserName="Student B" />);

    await waitFor(() => expect(markAsReadMutate).toHaveBeenCalledTimes(1));
  });

  it('marks messages again when a newer unread message appears', async () => {
    setHistoryMessages([buildMessage('msg-one', { read_by: [] })]);

    const { rerender } = render(<Chat {...baseProps} />);

    await waitFor(() => expect(markAsReadMutate).toHaveBeenCalledTimes(1));

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

    await waitFor(() => expect(markAsReadMutate).toHaveBeenCalledTimes(2));
  });
});
