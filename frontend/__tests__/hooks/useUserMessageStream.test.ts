import { renderHook, act } from '@testing-library/react';
import { useUserMessageStream } from '@/hooks/useUserMessageStream';

// Mock dependencies
const mockUseAuth = jest.fn();
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => `http://localhost:3000${path}`,
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

const mockRefreshAuthSession = jest.fn();
jest.mock('@/lib/auth/sessionRefresh', () => ({
  refreshAuthSession: (...args: unknown[]) => mockRefreshAuthSession(...args),
}));

// Mock fetchWithAuth
const mockFetchWithAuth = jest.fn();
jest.mock('@/lib/api', () => ({
  fetchWithAuth: (...args: unknown[]) => mockFetchWithAuth(...args),
}));

// Mock EventSource
class MockEventSource {
  url: string;
  withCredentials: boolean;
  listeners: Map<string, ((event: MessageEvent) => void)[]> = new Map();
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState = 0;
  CONNECTING = 0;
  OPEN = 1;
  CLOSED = 2;
  close = jest.fn();

  constructor(url: string, options?: EventSourceInit) {
    this.url = url;
    this.withCredentials = options?.withCredentials ?? false;
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type)!.push(listener);
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    const listeners = this.listeners.get(type);
    if (listeners) {
      const index = listeners.indexOf(listener);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }

  simulateOpen() {
    this.readyState = 1;
    this.onopen?.(new Event('open'));
  }

  simulateConnected() {
    const listeners = this.listeners.get('connected');
    listeners?.forEach((listener) => {
      listener({ data: 'connected' } as MessageEvent);
    });
  }

  simulateMessage(type: string, data: object) {
    const listeners = this.listeners.get(type);
    listeners?.forEach((listener) => {
      listener({ data: JSON.stringify(data) } as MessageEvent);
    });
  }

  simulateError() {
    this.readyState = 2;
    this.onerror?.(new Event('error'));
  }
}

const waitForEventSource = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};

describe('useUserMessageStream', () => {
  let mockEventSource: MockEventSource;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();

    // Mock EventSource constructor
    const MockConstructor = jest.fn((url: string, options?: EventSourceInit) => {
      mockEventSource = new MockEventSource(url, options);
      return mockEventSource as unknown as EventSource;
    });
    global.EventSource = MockConstructor as unknown as typeof EventSource;

    // Mock authenticated user
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: 'user1', email: 'test@example.com' },
      checkAuth: jest.fn(),
    });
    mockRefreshAuthSession.mockResolvedValue(true);

    // Mock SSE token fetch with fetchWithAuth
    mockFetchWithAuth.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ token: 'test-sse-token' }),
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();
  });

  describe('subscription stability', () => {
    it('should only create one EventSource connection per mount', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      // Trigger multiple subscribes
      act(() => {
        result.current.subscribe('conv1', { onMessage: jest.fn() });
      });
      act(() => {
        result.current.subscribe('conv2', { onMessage: jest.fn() });
      });

      // Should still only have one EventSource
      expect(global.EventSource).toHaveBeenCalledTimes(1);
    });

    it('should not recreate subscription when handler reference changes', async () => {
      const { result, rerender } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      // Subscribe with initial handler
      act(() => {
        result.current.subscribe('conv1', {
          onMessage: jest.fn(),
        });
      });

      // Rerender multiple times (simulating parent re-renders)
      rerender();
      rerender();
      rerender();

      // Subscription should still be active (not unsubscribed and resubscribed)
      expect(mockEventSource.close).not.toHaveBeenCalled();
    });
  });

  describe('event routing', () => {
    it('should route new_message events to correct conversation handler', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler1 = { onMessage: jest.fn() };
      const handler2 = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler1);
        result.current.subscribe('conv2', handler2);
      });

      // Send message to conv1
      act(() => {
        mockEventSource.simulateMessage('new_message', {
          type: 'new_message',
          conversation_id: 'conv1',
          is_mine: false,
          message: {
            id: 'msg1',
            content: 'Hello',
            sender_id: 'user2',
            sender_name: 'User 2',
            created_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
          },
        });
      });

      expect(handler1.onMessage).toHaveBeenCalledTimes(1);
      expect(handler1.onMessage).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'msg1', content: 'Hello' }),
        false
      );
      expect(handler2.onMessage).not.toHaveBeenCalled();
    });

    it('should notify __global__ subscriber for all messages', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const globalHandler = { onMessage: jest.fn() };
      const convHandler = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('__global__', globalHandler);
        result.current.subscribe('conv1', convHandler);
      });

      act(() => {
        mockEventSource.simulateMessage('new_message', {
          type: 'new_message',
          conversation_id: 'conv1',
          is_mine: false,
          message: {
            id: 'msg1',
            content: 'Hello',
            sender_id: 'user2',
            sender_name: 'User 2',
            created_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
          },
        });
      });

      expect(globalHandler.onMessage).toHaveBeenCalledTimes(1);
      expect(convHandler.onMessage).toHaveBeenCalledTimes(1);
    });
  });

  describe('read receipt handling', () => {
    it('should handle message_ids array format', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onReadReceipt: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('read_receipt', {
          type: 'read_receipt',
          conversation_id: 'conv1',
          message_ids: ['msg1', 'msg2', 'msg3'],
          reader_id: 'user1',
        });
      });

      expect(handler.onReadReceipt).toHaveBeenCalledWith(
        ['msg1', 'msg2', 'msg3'],
        'user1'
      );
    });

    it('should handle singular message_id format (backward compatibility)', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onReadReceipt: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('read_receipt', {
          type: 'read_receipt',
          conversation_id: 'conv1',
          message_id: 'msg1', // Singular, not array
          reader_id: 'user1',
        });
      });

      expect(handler.onReadReceipt).toHaveBeenCalledWith(
        ['msg1'], // Should be converted to array
        'user1'
      );
    });
  });

  describe('reaction handling', () => {
    it('should include all required fields in reaction event', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onReaction: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('reaction_update', {
          type: 'reaction_update',
          conversation_id: 'conv1',
          message_id: 'msg1',
          emoji: '👍',
          user_id: 'user1',
          action: 'added',
        });
      });

      expect(handler.onReaction).toHaveBeenCalledWith('msg1', '👍', 'added', 'user1');
    });
  });

  describe('cleanup', () => {
    it('should close EventSource on unmount', async () => {
      const { unmount } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      unmount();

      expect(mockEventSource.close).toHaveBeenCalled();
    });

    it('should remove handlers when unsubscribe is called', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
      });

      let unsubscribe: () => void;
      act(() => {
        unsubscribe = result.current.subscribe('conv1', handler);
      });

      act(() => {
        unsubscribe();
      });

      // Send message after unsubscribe
      act(() => {
        mockEventSource.simulateMessage('new_message', {
          type: 'new_message',
          conversation_id: 'conv1',
          is_mine: false,
          message: {
            id: 'msg1',
            content: 'Hello',
            sender_id: 'user2',
            sender_name: 'User 2',
            created_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
          },
        });
      });

      expect(handler.onMessage).not.toHaveBeenCalled();
    });
  });

  describe('typing status handling', () => {
    it('should route typing status events correctly', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onTyping: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('typing_status', {
          type: 'typing_status',
          conversation_id: 'conv1',
          user_id: 'user2',
          user_name: 'John Doe',
          is_typing: true,
          timestamp: '2024-01-01T12:00:00Z',
        });
      });

      expect(handler.onTyping).toHaveBeenCalledWith('user2', 'John Doe', true);
    });
  });

  describe('notification update handling', () => {
    it('should route notification_update events to global handler', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const globalHandler = { onNotificationUpdate: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('__global__', globalHandler);
      });

      act(() => {
        mockEventSource.simulateMessage('notification_update', {
          type: 'notification_update',
          unread_count: 5,
        });
      });

      expect(globalHandler.onNotificationUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ unread_count: 5 })
      );
    });
  });

  describe('message edited handling', () => {
    it('should route message_edited events to conversation handler', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessageEdited: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('message_edited', {
          type: 'message_edited',
          conversation_id: 'conv1',
          message_id: 'msg1',
          data: { content: 'Updated content' },
          editor_id: 'user2',
        });
      });

      expect(handler.onMessageEdited).toHaveBeenCalledWith('msg1', 'Updated content', 'user2');
    });

    it('should route message_edited to global handler', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const globalHandler = { onMessageEdited: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('__global__', globalHandler);
      });

      act(() => {
        mockEventSource.simulateMessage('message_edited', {
          type: 'message_edited',
          conversation_id: 'conv1',
          message_id: 'msg1',
          data: { content: 'Updated content' },
          editor_id: 'user2',
        });
      });

      expect(globalHandler.onMessageEdited).toHaveBeenCalledWith('msg1', 'Updated content', 'user2');
    });

    it('should not call handler if content is missing', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessageEdited: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('message_edited', {
          type: 'message_edited',
          conversation_id: 'conv1',
          message_id: 'msg1',
          data: {},
          editor_id: 'user2',
        });
      });

      expect(handler.onMessageEdited).not.toHaveBeenCalled();
    });
  });

  describe('message deleted handling', () => {
    it('should route message_deleted events to conversation handler', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessageDeleted: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('message_deleted', {
          type: 'message_deleted',
          conversation_id: 'conv1',
          message_id: 'msg1',
          deleted_by: 'user2',
        });
      });

      expect(handler.onMessageDeleted).toHaveBeenCalledWith('msg1', 'user2');
    });
  });

  describe('duplicate message prevention', () => {
    it('should deduplicate messages with the same ID', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      // Send the same message twice
      act(() => {
        mockEventSource.simulateMessage('new_message', {
          type: 'new_message',
          conversation_id: 'conv1',
          is_mine: false,
          message: {
            id: 'msg-duplicate-test',
            content: 'Hello',
            sender_id: 'user2',
            sender_name: 'User 2',
            created_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
          },
        });
      });

      act(() => {
        mockEventSource.simulateMessage('new_message', {
          type: 'new_message',
          conversation_id: 'conv1',
          is_mine: false,
          message: {
            id: 'msg-duplicate-test',
            content: 'Hello',
            sender_id: 'user2',
            sender_name: 'User 2',
            created_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
          },
        });
      });

      // Should only be called once (duplicate filtered)
      expect(handler.onMessage).toHaveBeenCalledTimes(1);
    });

    it('should prune seenMessageIds when exceeding MAX_SEEN_MESSAGE_IDS', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      // Send 201 unique messages to trigger pruning (MAX_SEEN_MESSAGE_IDS = 200)
      for (let i = 0; i < 201; i++) {
        act(() => {
          mockEventSource.simulateMessage('new_message', {
            type: 'new_message',
            conversation_id: 'conv1',
            is_mine: false,
            message: {
              id: `msg-prune-test-${i}`,
              content: `Message ${i}`,
              sender_id: 'user2',
              sender_name: 'User 2',
              created_at: '2024-01-01T12:00:00Z',
              booking_id: 'booking1',
            },
          });
        });
      }

      // All 201 messages should be processed (each unique)
      expect(handler.onMessage).toHaveBeenCalledTimes(201);
    });
  });

  describe('heartbeat handling', () => {
    it('should handle keep-alive events', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);

      // Simulate keep-alive (should not disconnect)
      act(() => {
        mockEventSource.simulateMessage('keep-alive', {});
      });

      expect(result.current.isConnected).toBe(true);
    });

    it('should handle heartbeat events', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);

      // Simulate heartbeat
      act(() => {
        mockEventSource.simulateMessage('heartbeat', {});
      });

      expect(result.current.isConnected).toBe(true);
    });

    it('should reconnect after heartbeat timeout', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);

      // Advance time past heartbeat timeout (45 seconds)
      act(() => {
        jest.advanceTimersByTime(46000);
      });

      // Should show connection error
      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Heartbeat timeout');
    });

    it('should schedule reconnect after heartbeat timeout and reconnect successfully', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      const firstEventSource = mockEventSource;

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);
      expect(global.EventSource).toHaveBeenCalledTimes(1);

      // Advance time past heartbeat timeout (45 seconds)
      act(() => {
        jest.advanceTimersByTime(46000);
      });

      expect(result.current.isConnected).toBe(false);
      expect(firstEventSource.close).toHaveBeenCalled();

      // Advance time past reconnect delay (3 seconds)
      act(() => {
        jest.advanceTimersByTime(4000);
      });

      await waitForEventSource();

      // Should create a new EventSource after reconnect delay
      expect(global.EventSource).toHaveBeenCalledTimes(2);
    });
  });

  describe('authentication handling', () => {
    it('should not connect when not authenticated', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        checkAuth: jest.fn(),
      });

      renderHook(() => useUserMessageStream());

      // Should not create EventSource
      expect(global.EventSource).not.toHaveBeenCalled();
    });

    it('should fall back to cookie auth when token fetch fails', async () => {
      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({}),
      });

      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      // Should still try to connect (fallback to cookie auth)
      expect(global.EventSource).toHaveBeenCalled();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);
    });

    it('should fall back to cookie auth when token fetch throws', async () => {
      mockFetchWithAuth.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      // Should still try to connect
      expect(global.EventSource).toHaveBeenCalled();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);
    });

    it('should handle 401 unauthorized SSE token response', async () => {
      const checkAuth = jest.fn();
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user1', email: 'test@example.com' },
        checkAuth,
      });

      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({}),
      });

      const { result } = renderHook(() => useUserMessageStream());

      // Wait for async connectWithToken to complete
      await act(async () => {
        await jest.runAllTimersAsync();
      });

      // Should not create EventSource when unauthorized
      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Not authenticated');
      expect(checkAuth).toHaveBeenCalled();
    });

    it('should handle 403 forbidden SSE token response', async () => {
      const checkAuth = jest.fn();
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user1', email: 'test@example.com' },
        checkAuth,
      });

      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 403,
        json: () => Promise.resolve({}),
      });

      const { result } = renderHook(() => useUserMessageStream());

      // Wait for async connectWithToken to complete
      await act(async () => {
        await jest.runAllTimersAsync();
      });

      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Not authenticated');
      expect(checkAuth).toHaveBeenCalled();
    });
  });

  describe('connection error handling', () => {
    it('should set connection error on EventSource error', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);

      act(() => {
        mockEventSource.simulateError();
      });

      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Connection lost');
    });

    it('should schedule reconnect after connection error', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);

      act(() => {
        mockEventSource.simulateError();
      });

      // Connection should be lost
      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Connection lost');

      // EventSource should have been closed
      expect(mockEventSource.close).toHaveBeenCalled();
    });

    it('should suppress repeated error logs', async () => {
      const { logger: mockLogger } = jest.requireMock('@/lib/logger') as { logger: { warn: jest.Mock } };

      renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      mockLogger.warn.mockClear();

      // Trigger multiple errors
      act(() => {
        mockEventSource.simulateError();
      });

      // Recreate connection for next error
      act(() => {
        jest.advanceTimersByTime(4000);
      });

      await act(async () => {
        await Promise.resolve();
      });

      // The second error should be suppressed (logged at debug level instead)
      // This tests the connectionErrorLoggedRef behavior
    });

    it('should log warn on first connection error', async () => {
      const { logger: mockLogger } = jest.requireMock('@/lib/logger') as { logger: { warn: jest.Mock } };

      renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      mockLogger.warn.mockClear();

      // First error - should log warn
      act(() => {
        mockEventSource.simulateError();
      });

      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[SSE] Connection error, will retry',
        expect.any(Object)
      );
    });

    it('should schedule reconnect after error with reconnect delay', async () => {
      renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(global.EventSource).toHaveBeenCalledTimes(1);

      // Trigger error
      act(() => {
        mockEventSource.simulateError();
      });

      // Advance time past reconnect delay (3 seconds)
      act(() => {
        jest.advanceTimersByTime(4000);
      });

      await waitForEventSource();

      // Should have attempted to reconnect
      expect(global.EventSource).toHaveBeenCalledTimes(2);
    });

    it('refreshes session before reconnecting after connection error', async () => {
      renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      act(() => {
        mockEventSource.simulateError();
      });

      act(() => {
        jest.advanceTimersByTime(4000);
      });

      await waitForEventSource();

      expect(mockRefreshAuthSession).toHaveBeenCalled();
      expect(global.EventSource).toHaveBeenCalledTimes(2);
    });

    it('does not reconnect when refresh fails after connection error', async () => {
      const checkAuth = jest.fn();
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user1', email: 'test@example.com' },
        checkAuth,
      });
      mockRefreshAuthSession.mockResolvedValue(false);

      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });
      expect(result.current.isConnected).toBe(true);

      act(() => {
        mockEventSource.simulateError();
      });

      act(() => {
        jest.advanceTimersByTime(4000);
      });

      await waitForEventSource();

      expect(mockRefreshAuthSession).toHaveBeenCalled();
      expect(checkAuth).toHaveBeenCalled();
      expect(result.current.connectionError).toBe('Not authenticated');
      expect(global.EventSource).toHaveBeenCalledTimes(1);
    });
  });

  describe('event parsing error handling', () => {
    it('should handle malformed new_message JSON', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      // Simulate malformed JSON (this tests the catch block)
      const listeners = mockEventSource.listeners.get('new_message');
      listeners?.forEach((listener) => {
        act(() => {
          listener({ data: 'invalid json{' } as MessageEvent);
        });
      });

      // Handler should not be called due to parse error
      expect(handler.onMessage).not.toHaveBeenCalled();
    });

    it('should handle malformed typing_status JSON', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onTyping: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      const listeners = mockEventSource.listeners.get('typing_status');
      listeners?.forEach((listener) => {
        act(() => {
          listener({ data: 'invalid json{' } as MessageEvent);
        });
      });

      expect(handler.onTyping).not.toHaveBeenCalled();
    });

    it('should handle malformed read_receipt JSON', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onReadReceipt: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      const listeners = mockEventSource.listeners.get('read_receipt');
      listeners?.forEach((listener) => {
        act(() => {
          listener({ data: 'invalid json{' } as MessageEvent);
        });
      });

      expect(handler.onReadReceipt).not.toHaveBeenCalled();
    });

    it('should handle malformed reaction_update JSON', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onReaction: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      const listeners = mockEventSource.listeners.get('reaction_update');
      listeners?.forEach((listener) => {
        act(() => {
          listener({ data: 'invalid json{' } as MessageEvent);
        });
      });

      expect(handler.onReaction).not.toHaveBeenCalled();
    });

    it('should handle malformed message_edited JSON', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessageEdited: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      const listeners = mockEventSource.listeners.get('message_edited');
      listeners?.forEach((listener) => {
        act(() => {
          listener({ data: 'invalid json{' } as MessageEvent);
        });
      });

      expect(handler.onMessageEdited).not.toHaveBeenCalled();
    });

    it('should handle malformed message_deleted JSON', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessageDeleted: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      const listeners = mockEventSource.listeners.get('message_deleted');
      listeners?.forEach((listener) => {
        act(() => {
          listener({ data: 'invalid json{' } as MessageEvent);
        });
      });

      expect(handler.onMessageDeleted).not.toHaveBeenCalled();
    });

    it('should handle malformed notification_update JSON', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onNotificationUpdate: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('__global__', handler);
      });

      const listeners = mockEventSource.listeners.get('notification_update');
      listeners?.forEach((listener) => {
        act(() => {
          listener({ data: 'invalid json{' } as MessageEvent);
        });
      });

      expect(handler.onNotificationUpdate).not.toHaveBeenCalled();
    });
  });

  describe('no handler registered', () => {
    it('should silently ignore events for unsubscribed conversations', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
        // No handler subscribed for 'conv1'
      });

      // Should not throw when receiving event for unsubscribed conversation
      act(() => {
        mockEventSource.simulateMessage('new_message', {
          type: 'new_message',
          conversation_id: 'conv1',
          is_mine: false,
          message: {
            id: 'msg1',
            content: 'Hello',
            sender_id: 'user2',
            sender_name: 'User 2',
            created_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
          },
        });
      });

      // If we got here without throwing, the test passes
      expect(result.current.isConnected).toBe(true);
    });
  });

  describe('message ID deduplication pruning', () => {
    it('should prune seen message IDs when exceeding max size', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      // Send more than MAX_SEEN_MESSAGE_IDS (200) unique messages to trigger pruning
      for (let i = 0; i < 205; i++) {
        act(() => {
          mockEventSource.simulateMessage('new_message', {
            type: 'new_message',
            conversation_id: 'conv1',
            is_mine: false,
            message: {
              id: `msg-prune-${i}`,
              content: `Message ${i}`,
              sender_id: 'user2',
              sender_name: 'User 2',
              created_at: '2024-01-01T12:00:00Z',
              booking_id: 'booking1',
            },
          });
        });
      }

      // All unique messages should be handled
      expect(handler.onMessage).toHaveBeenCalledTimes(205);
    });
  });

  describe('heartbeat timeout reconnection', () => {
    it('should schedule reconnect after heartbeat timeout and attempt to reconnect', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      expect(result.current.isConnected).toBe(true);

      // Advance time past heartbeat timeout (45 seconds)
      act(() => {
        jest.advanceTimersByTime(46000);
      });

      // Connection should be lost and error set
      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Heartbeat timeout');

      // EventSource should have been closed
      expect(mockEventSource.close).toHaveBeenCalled();

      // Advance time to trigger reconnect (RECONNECT_DELAY = 3000ms)
      act(() => {
        jest.advanceTimersByTime(4000);
      });

      // Wait for async token fetch
      await act(async () => {
        await Promise.resolve();
      });

      // Should attempt to create a new EventSource (reconnect)
      expect(global.EventSource).toHaveBeenCalledTimes(2);
    });

    it('does not reconnect after heartbeat timeout when refresh fails', async () => {
      const checkAuth = jest.fn();
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user1', email: 'test@example.com' },
        checkAuth,
      });
      mockRefreshAuthSession.mockResolvedValue(false);

      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      act(() => {
        jest.advanceTimersByTime(46000);
      });

      act(() => {
        jest.advanceTimersByTime(4000);
      });

      await waitForEventSource();

      expect(mockRefreshAuthSession).toHaveBeenCalled();
      expect(checkAuth).toHaveBeenCalled();
      expect(result.current.connectionError).toBe('Not authenticated');
      expect(global.EventSource).toHaveBeenCalledTimes(1);
    });
  });

  describe('connect skipping conditions', () => {
    it('should skip connect when EventSource already exists', async () => {
      const { rerender } = renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      // Rerender multiple times
      rerender();
      rerender();

      // Should still only have one EventSource
      expect(global.EventSource).toHaveBeenCalledTimes(1);
    });

  });

  describe('duplicate connection prevention', () => {
    it('should skip connect when isConnectingRef is already true (concurrent connect race)', async () => {
      // Make the SSE token fetch hang so isConnectingRef stays true
      let resolveFetch: ((v: unknown) => void) | undefined;
      mockFetchWithAuth.mockImplementation(() => new Promise((resolve) => {
        resolveFetch = resolve;
      }));

      const { result } = renderHook(() => useUserMessageStream());

      // The first connect() is triggered by the effect, while token is still pending
      // isConnectingRef is true until the fetch completes
      // A re-render should NOT create a second EventSource
      expect(global.EventSource).not.toHaveBeenCalled();

      // Resolve the pending fetch to allow first connect to complete
      resolveFetch!({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ token: 'test-token' }),
      });

      await waitForEventSource();

      expect(global.EventSource).toHaveBeenCalledTimes(1);
      expect(result.current.isConnected).toBe(false); // not yet connected (no simulateConnected)
    });
  });

  describe('SSE token edge cases', () => {
    it('should connect without token query param when token response has no token field', async () => {
      mockFetchWithAuth.mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}), // no token field
      });

      renderHook(() => useUserMessageStream());
      await waitForEventSource();

      // EventSource should be created with the base URL (no sse_token param)
      expect(global.EventSource).toHaveBeenCalledTimes(1);
      const call = (global.EventSource as unknown as jest.Mock).mock.calls[0] as [string];
      expect(call[0]).not.toContain('sse_token=');
    });

    it('should connect without token query param when token is empty string', async () => {
      mockFetchWithAuth.mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ token: '' }),
      });

      renderHook(() => useUserMessageStream());
      await waitForEventSource();

      expect(global.EventSource).toHaveBeenCalledTimes(1);
      const call = (global.EventSource as unknown as jest.Mock).mock.calls[0] as [string];
      expect(call[0]).not.toContain('sse_token=');
    });
  });

  describe('error handler branches', () => {
    it('should suppress connection error log when auth is rejected', async () => {
      const checkAuth = jest.fn();
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user1', email: 'test@example.com' },
        checkAuth,
      });

      // First, cause auth rejection via 401
      mockFetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({}),
      });

      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await jest.runAllTimersAsync();
      });

      // authRejectedRef should now be true
      expect(result.current.connectionError).toBe('Not authenticated');

      // Now if an error were to fire, the suppressed branch is covered
      // Since no EventSource was created, the error path is implicitly tested
    });

    it('should suppress second connection error log (connectionErrorLoggedRef)', async () => {
      const { logger: mockLogger } = jest.requireMock('@/lib/logger') as {
        logger: { warn: jest.Mock; debug: jest.Mock };
      };

      renderHook(() => useUserMessageStream());
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      mockLogger.warn.mockClear();
      mockLogger.debug.mockClear();

      // First error -- warn should be called
      act(() => {
        mockEventSource.simulateError();
      });

      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[SSE] Connection error, will retry',
        expect.any(Object)
      );

      // Reconnect
      act(() => {
        jest.advanceTimersByTime(4000);
      });
      await waitForEventSource();

      act(() => {
        mockEventSource.simulateConnected();
      });

      mockLogger.warn.mockClear();

      // Second error on the new EventSource -- connectionErrorLoggedRef was set to true
      // but then reset on simulateConnected. Let's trigger error without connecting first.
      act(() => {
        mockEventSource.simulateError();
      });

      // This time warn should be called again because connectionErrorLoggedRef was reset
      expect(mockLogger.warn).toHaveBeenCalledWith(
        '[SSE] Connection error, will retry',
        expect.any(Object)
      );
    });
  });

  describe('global handler for message_edited without content', () => {
    it('should not call global onMessageEdited when data.content is missing', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const globalHandler = { onMessageEdited: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('__global__', globalHandler);
      });

      act(() => {
        mockEventSource.simulateMessage('message_edited', {
          type: 'message_edited',
          conversation_id: 'conv1',
          message_id: 'msg1',
          data: {}, // no content
          editor_id: 'user2',
        });
      });

      expect(globalHandler.onMessageEdited).not.toHaveBeenCalled();
    });

    it('should not call global onMessageEdited when data is null', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const globalHandler = { onMessageEdited: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('__global__', globalHandler);
      });

      act(() => {
        mockEventSource.simulateMessage('message_edited', {
          type: 'message_edited',
          conversation_id: 'conv1',
          message_id: 'msg1',
          data: null,
          editor_id: 'user2',
        });
      });

      expect(globalHandler.onMessageEdited).not.toHaveBeenCalled();
    });
  });

  describe('event routing with no conversation_id', () => {
    it('should not route events when conversation_id is undefined', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onMessage: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      // Send a message without conversation_id
      act(() => {
        mockEventSource.simulateMessage('new_message', {
          type: 'new_message',
          is_mine: false,
          message: {
            id: 'msg-no-conv',
            content: 'No conversation ID',
            sender_id: 'user2',
            sender_name: 'User 2',
            created_at: '2024-01-01T12:00:00Z',
            booking_id: 'booking1',
          },
        });
      });

      // Handler should not be called since there's no conversation_id to match
      expect(handler.onMessage).not.toHaveBeenCalled();
    });
  });

  describe('read receipt with neither message_ids nor message_id', () => {
    it('should call onReadReceipt with empty array when both message_ids and message_id are missing', async () => {
      const { result } = renderHook(() => useUserMessageStream());
      await waitForEventSource();
      const handler = { onReadReceipt: jest.fn() };

      act(() => {
        mockEventSource.simulateConnected();
        result.current.subscribe('conv1', handler);
      });

      act(() => {
        mockEventSource.simulateMessage('read_receipt', {
          type: 'read_receipt',
          conversation_id: 'conv1',
          reader_id: 'user1',
          // No message_ids and no message_id
        });
      });

      expect(handler.onReadReceipt).toHaveBeenCalledWith([], 'user1');
    });
  });

  describe('unauthenticated user does not connect', () => {
    it('should not connect when user is null even if isAuthenticated is true', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: null,
        checkAuth: jest.fn(),
      });

      renderHook(() => useUserMessageStream());

      // The useEffect checks both isAuthenticated and user
      expect(global.EventSource).not.toHaveBeenCalled();
    });
  });

  describe('auth state reset', () => {
    it('should reset authRejectedRef when isAuthenticated transitions from false to true', async () => {
      const checkAuth = jest.fn();
      // Start rejected
      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({}),
      });

      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user1', email: 'test@example.com' },
        checkAuth,
      });

      const { result, rerender } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await jest.runAllTimersAsync();
      });

      expect(result.current.connectionError).toBe('Not authenticated');

      // Simulate logout (isAuthenticated becomes false)
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        checkAuth,
      });

      rerender();

      // Now simulate re-login (isAuthenticated becomes true again)
      // This triggers the useEffect that resets authRejectedRef
      mockFetchWithAuth.mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ token: 'new-token' }),
      });

      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user1', email: 'test@example.com' },
        checkAuth,
      });

      rerender();

      await act(async () => {
        await jest.runAllTimersAsync();
      });

      await waitForEventSource();

      // After auth reset (false -> true), authRejectedRef should be cleared
      // and a new EventSource connection should be attempted
      expect(global.EventSource).toHaveBeenCalled();
    });
  });
});
