import { renderHook, waitFor, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useMessageConfig,
  useUnreadCount,
  useConversationMessages,
  useMarkMessagesAsRead,
  useDeleteMessage,
  useEditMessage,
  useAddReaction,
  useRemoveReaction,
  fetchMessageConfig,
  fetchUnreadCount,
  markMessagesAsReadImperative,
  deleteMessageImperative,
} from '../messages';

// Mock withApiBase to return the path as-is
jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => `http://localhost${path}`,
}));

const createTestQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
};

const createWrapper = () => {
  const queryClient = createTestQueryClient();
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'TestQueryWrapper';
  return Wrapper;
};

describe('messages service', () => {
  let originalFetch: typeof global.fetch;

  beforeEach(() => {
    originalFetch = global.fetch;
    jest.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe('useMessageConfig', () => {
    it('fetches message config successfully', async () => {
      const mockConfig = { edit_window_minutes: 15 };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockConfig,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useMessageConfig(), { wrapper: createWrapper() });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockConfig);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost/api/v1/messages/config',
        expect.objectContaining({
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
        })
      );
    });

    it('throws error on failed fetch', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useMessageConfig(), { wrapper: createWrapper() });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to load message config');
    });
  });

  describe('useUnreadCount', () => {
    it('fetches unread count successfully', async () => {
      const mockData = { unread_count: 5 };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockData,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useUnreadCount(), { wrapper: createWrapper() });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
    });

    it('throws error on failed fetch', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 401,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useUnreadCount(), { wrapper: createWrapper() });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to load unread count');
    });

    it('respects enabled parameter', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ unread_count: 0 }),
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useUnreadCount(false), { wrapper: createWrapper() });

      // Query should not be fetched
      expect(mockFetch).not.toHaveBeenCalled();
      expect(result.current.data).toBeUndefined();
    });
  });

  describe('useConversationMessages', () => {
    it('fetches conversation messages successfully', async () => {
      const mockData = {
        messages: [{ id: 'msg-1', content: 'Hello' }],
        has_more: false,
      };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockData,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(
        () => useConversationMessages('conv-123'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/conversations/conv-123/messages'),
        expect.any(Object)
      );
    });

    it('respects limit parameter', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ messages: [], has_more: false }),
      });
      global.fetch = mockFetch;

      renderHook(
        () => useConversationMessages('conv-123', 25),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      const calledUrl = mockFetch.mock.calls[0][0] as string;
      expect(calledUrl).toContain('limit=25');
    });

    it('respects before parameter for pagination', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ messages: [], has_more: false }),
      });
      global.fetch = mockFetch;

      renderHook(
        () => useConversationMessages('conv-123', 50, 'msg-cursor'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });

      const calledUrl = mockFetch.mock.calls[0][0] as string;
      expect(calledUrl).toContain('before=msg-cursor');
    });

    it('respects enabled parameter', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ messages: [] }),
      });
      global.fetch = mockFetch;

      renderHook(
        () => useConversationMessages('conv-123', 50, undefined, false),
        { wrapper: createWrapper() }
      );

      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('does not fetch when conversationId is undefined', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ messages: [] }),
      });
      global.fetch = mockFetch;

      renderHook(
        () => useConversationMessages(undefined),
        { wrapper: createWrapper() }
      );

      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('throws error on failed fetch', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 404,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(
        () => useConversationMessages('conv-123'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to fetch conversation messages');
    });

    it('calls onSuccess callback when provided', async () => {
      const mockData = { messages: [], has_more: false };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockData,
      });
      global.fetch = mockFetch;

      const onSuccess = jest.fn();

      const { result } = renderHook(
        () => useConversationMessages('conv-123', 50, undefined, true, { onSuccess }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Wait for useEffect to trigger
      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalledWith(mockData);
      });
    });

    it('calls onError callback when provided', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });
      global.fetch = mockFetch;

      const onError = jest.fn();

      const { result } = renderHook(
        () => useConversationMessages('conv-123', 50, undefined, true, { onError }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      await waitFor(() => {
        expect(onError).toHaveBeenCalled();
      });
    });
  });

  describe('useMarkMessagesAsRead', () => {
    it('marks messages as read successfully', async () => {
      const mockResult = { marked_count: 3 };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useMarkMessagesAsRead(), { wrapper: createWrapper() });

      await act(async () => {
        await result.current.mutateAsync({ conversation_id: 'conv-123' });
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost/api/v1/messages/mark-read',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ conversation_id: 'conv-123' }),
        })
      );
    });

    it('marks specific message IDs as read', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ marked_count: 2 }),
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useMarkMessagesAsRead(), { wrapper: createWrapper() });

      await act(async () => {
        await result.current.mutateAsync({ message_ids: ['msg-1', 'msg-2'] });
      });

      const callBody = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(callBody.message_ids).toEqual(['msg-1', 'msg-2']);
    });

    it('throws error on failure', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () => 'Invalid request',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useMarkMessagesAsRead(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({ conversation_id: 'conv-123' });
        })
      ).rejects.toThrow('Invalid request');
    });

    it('throws default error message when no text returned', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => '',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useMarkMessagesAsRead(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({ conversation_id: 'conv-123' });
        })
      ).rejects.toThrow('Failed to mark messages as read (status 500)');
    });
  });

  describe('useDeleteMessage', () => {
    it('deletes message successfully', async () => {
      const mockResult = { deleted: true };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useDeleteMessage(), { wrapper: createWrapper() });

      const response = await act(async () => {
        return result.current.mutateAsync({ messageId: 'msg-123' });
      });

      expect(response).toEqual(mockResult);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost/api/v1/messages/msg-123',
        expect.objectContaining({
          method: 'DELETE',
        })
      );
    });

    it('throws error on failure', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 403,
        text: async () => 'Forbidden',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useDeleteMessage(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({ messageId: 'msg-123' });
        })
      ).rejects.toThrow('Forbidden');
    });

    it('throws default error when no text returned', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => '',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useDeleteMessage(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({ messageId: 'msg-123' });
        })
      ).rejects.toThrow('Failed to delete message');
    });
  });

  describe('useEditMessage', () => {
    it('edits message successfully', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useEditMessage(), { wrapper: createWrapper() });

      await act(async () => {
        await result.current.mutateAsync({
          messageId: 'msg-123',
          data: { content: 'Updated content' },
        });
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost/api/v1/messages/msg-123',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ content: 'Updated content' }),
        })
      );
    });

    it('throws error on failure', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () => 'Edit window expired',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useEditMessage(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({
            messageId: 'msg-123',
            data: { content: 'Updated' },
          });
        })
      ).rejects.toThrow('Edit window expired');
    });

    it('throws default error when no text returned', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => '',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useEditMessage(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({
            messageId: 'msg-123',
            data: { content: 'Updated' },
          });
        })
      ).rejects.toThrow('Failed to edit message');
    });
  });

  describe('useAddReaction', () => {
    it('adds reaction successfully', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useAddReaction(), { wrapper: createWrapper() });

      await act(async () => {
        await result.current.mutateAsync({
          messageId: 'msg-123',
          data: { emoji: '👍' },
        });
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost/api/v1/messages/msg-123/reactions',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ emoji: '👍' }),
        })
      );
    });

    it('throws error on failure', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () => 'Invalid emoji',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useAddReaction(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({
            messageId: 'msg-123',
            data: { emoji: '👍' },
          });
        })
      ).rejects.toThrow('Invalid emoji');
    });

    it('throws default error when no text returned', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => '',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useAddReaction(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({
            messageId: 'msg-123',
            data: { emoji: '👍' },
          });
        })
      ).rejects.toThrow('Failed to add reaction');
    });
  });

  describe('useRemoveReaction', () => {
    it('removes reaction successfully', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useRemoveReaction(), { wrapper: createWrapper() });

      await act(async () => {
        await result.current.mutateAsync({
          messageId: 'msg-123',
          data: { emoji: '👍' },
        });
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost/api/v1/messages/msg-123/reactions',
        expect.objectContaining({
          method: 'DELETE',
          body: JSON.stringify({ emoji: '👍' }),
        })
      );
    });

    it('throws error on failure', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => 'Reaction not found',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useRemoveReaction(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({
            messageId: 'msg-123',
            data: { emoji: '👍' },
          });
        })
      ).rejects.toThrow('Reaction not found');
    });

    it('throws default error when no text returned', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => '',
      });
      global.fetch = mockFetch;

      const { result } = renderHook(() => useRemoveReaction(), { wrapper: createWrapper() });

      await expect(
        act(async () => {
          await result.current.mutateAsync({
            messageId: 'msg-123',
            data: { emoji: '👍' },
          });
        })
      ).rejects.toThrow('Failed to remove reaction');
    });
  });

  describe('fetchMessageConfig (imperative)', () => {
    it('fetches config successfully', async () => {
      const mockConfig = { edit_window_minutes: 15 };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockConfig,
      });
      global.fetch = mockFetch;

      const result = await fetchMessageConfig();

      expect(result).toEqual(mockConfig);
    });

    it('throws error on failure', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });
      global.fetch = mockFetch;

      await expect(fetchMessageConfig()).rejects.toThrow(
        'Failed to fetch message config (status 500)'
      );
    });
  });

  describe('fetchUnreadCount (imperative)', () => {
    it('fetches unread count successfully', async () => {
      const mockData = { unread_count: 3 };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockData,
      });
      global.fetch = mockFetch;

      const result = await fetchUnreadCount();

      expect(result).toEqual(mockData);
    });

    it('throws error on failure', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 401,
      });
      global.fetch = mockFetch;

      await expect(fetchUnreadCount()).rejects.toThrow(
        'Failed to fetch unread count (status 401)'
      );
    });
  });

  describe('markMessagesAsReadImperative', () => {
    it('marks messages as read successfully', async () => {
      const mockResult = { marked_count: 5 };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      });
      global.fetch = mockFetch;

      const result = await markMessagesAsReadImperative({ conversation_id: 'conv-123' });

      expect(result).toEqual(mockResult);
    });

    it('throws error with message from response', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () => 'Invalid conversation ID',
      });
      global.fetch = mockFetch;

      await expect(
        markMessagesAsReadImperative({ conversation_id: 'invalid' })
      ).rejects.toThrow('Invalid conversation ID');
    });

    it('throws default error when no text returned', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => '',
      });
      global.fetch = mockFetch;

      await expect(
        markMessagesAsReadImperative({ conversation_id: 'conv-123' })
      ).rejects.toThrow('Failed to mark messages as read (status 500)');
    });
  });

  describe('deleteMessageImperative', () => {
    it('deletes message successfully', async () => {
      const mockResult = { deleted: true };
      const mockFetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResult,
      });
      global.fetch = mockFetch;

      const result = await deleteMessageImperative('msg-123');

      expect(result).toEqual(mockResult);
    });

    it('throws error with message from response', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 403,
        text: async () => 'Permission denied',
      });
      global.fetch = mockFetch;

      await expect(deleteMessageImperative('msg-123')).rejects.toThrow('Permission denied');
    });

    it('throws default error when no text returned', async () => {
      const mockFetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => '',
      });
      global.fetch = mockFetch;

      await expect(deleteMessageImperative('msg-123')).rejects.toThrow(
        'Failed to delete message (status 404)'
      );
    });
  });
});
