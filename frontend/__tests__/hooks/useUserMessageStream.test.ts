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

    // Mock SSE token fetch
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ token: 'test-sse-token' }),
    }) as jest.Mock;
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
});
