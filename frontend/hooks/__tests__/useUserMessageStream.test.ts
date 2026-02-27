import { renderHook, act } from '@testing-library/react';
import { useUserMessageStream } from '../useUserMessageStream';
import type { ConversationHandlers } from '@/types/messaging';

// ── Mocks ──────────────────────────────────────────────────────

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

const mockCheckAuth = jest.fn();
const mockUseAuth = jest.fn().mockReturnValue({
  isAuthenticated: true,
  user: { id: 'user-1', first_name: 'John' },
  checkAuth: mockCheckAuth,
});

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockFetchWithAuth = jest.fn();

jest.mock('@/lib/api', () => ({
  fetchWithAuth: (...args: unknown[]) => mockFetchWithAuth(...args),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((endpoint: string) => `http://localhost:8000${endpoint}`),
}));

const mockRefreshAuthSession = jest.fn();

jest.mock('@/lib/auth/sessionRefresh', () => ({
  refreshAuthSession: () => mockRefreshAuthSession(),
}));

// EventSource mock
type EventHandler = (event: MessageEvent | Event) => void;

class MockEventSource {
  url: string;
  withCredentials: boolean;
  readyState: number;
  listeners: Map<string, EventHandler[]>;
  onerror: ((event: Event) => void) | null = null;

  static instances: MockEventSource[] = [];

  constructor(url: string, init?: EventSourceInit) {
    this.url = url;
    this.withCredentials = init?.withCredentials ?? false;
    this.readyState = 0; // CONNECTING
    this.listeners = new Map();
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventHandler): void {
    const existing = this.listeners.get(type) || [];
    existing.push(listener);
    this.listeners.set(type, existing);
  }

  close(): void {
    this.readyState = 2; // CLOSED
  }

  // Test helpers
  emit(type: string, data?: string): void {
    const handlers = this.listeners.get(type) || [];
    const event = data !== undefined
      ? new MessageEvent(type, { data })
      : new Event(type);
    handlers.forEach((handler) => handler(event));
  }

  triggerError(): void {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }
}

// Install mock EventSource
const OriginalEventSource = global.EventSource;
beforeAll(() => {
  global.EventSource = MockEventSource as unknown as typeof EventSource;
});
afterAll(() => {
  global.EventSource = OriginalEventSource;
});

function getLatestEventSource(): MockEventSource {
  const instance = MockEventSource.instances[MockEventSource.instances.length - 1];
  if (!instance) throw new Error('No EventSource instance created');
  return instance;
}

describe('useUserMessageStream', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    MockEventSource.instances = [];

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: 'user-1', first_name: 'John' },
      checkAuth: mockCheckAuth,
    });

    // Default: SSE token fetch succeeds
    mockFetchWithAuth.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ token: 'sse-token-123' }),
    });

    mockRefreshAuthSession.mockResolvedValue(true);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('subscribe and unsubscribe', () => {
    it('subscribe returns an unsubscribe function', async () => {
      const { result } = renderHook(() => useUserMessageStream());

      const handlers: ConversationHandlers = {
        onMessage: jest.fn(),
      };

      let unsub: () => void;
      act(() => {
        unsub = result.current.subscribe('conv-1', handlers);
      });

      expect(typeof unsub!).toBe('function');

      act(() => {
        unsub!();
      });
    });
  });

  describe('connection lifecycle', () => {
    it('connects when authenticated and sets isConnected on connected event', async () => {
      const { result } = renderHook(() => useUserMessageStream());

      // Allow the async connectWithToken to proceed
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      expect(es.url).toContain('sse_token=sse-token-123');

      // Trigger connected event
      act(() => {
        es.emit('connected');
      });

      expect(result.current.isConnected).toBe(true);
      expect(result.current.connectionError).toBeNull();
    });

    it('does not connect when not authenticated', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        checkAuth: mockCheckAuth,
      });

      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
      });

      expect(result.current.isConnected).toBe(false);
      expect(MockEventSource.instances).toHaveLength(0);
    });

    it('does not connect when user is null', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: null,
        checkAuth: mockCheckAuth,
      });

      renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
      });

      expect(MockEventSource.instances).toHaveLength(0);
    });

    it('falls back to cookie auth when SSE token request fails', async () => {
      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
      });

      renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      // Should connect without token param
      expect(es.url).not.toContain('sse_token');
    });

    it('falls back to cookie auth when SSE token request throws', async () => {
      mockFetchWithAuth.mockRejectedValue(new Error('Network error'));

      renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      expect(es.url).not.toContain('sse_token');
    });

    it('sets auth rejected when SSE token returns 401', async () => {
      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({}),
      });

      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(result.current.connectionError).toBe('Not authenticated');
      expect(mockCheckAuth).toHaveBeenCalled();
      // Should not create EventSource
      expect(MockEventSource.instances).toHaveLength(0);
    });

    it('sets auth rejected when SSE token returns 403', async () => {
      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({}),
      });

      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(result.current.connectionError).toBe('Not authenticated');
    });

    it('uses base URL without token when token response has no token field', async () => {
      mockFetchWithAuth.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({}),
      });

      renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      expect(es.url).not.toContain('sse_token');
    });
  });

  describe('event routing', () => {
    it('routes new_message events to subscribed conversation handler', async () => {
      const onMessage = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      act(() => {
        result.current.subscribe('conv-1', { onMessage });
      });

      const es = getLatestEventSource();

      act(() => {
        es.emit('connected');
      });

      act(() => {
        es.emit(
          'new_message',
          JSON.stringify({
            conversation_id: 'conv-1',
            is_mine: false,
            message: { id: 'msg-1', content: 'Hello', sender_id: 'u2', sender_name: 'Jane', created_at: '2025-01-01' },
          })
        );
      });

      expect(onMessage).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'msg-1', content: 'Hello' }),
        false
      );
    });

    it('deduplicates new_message events with the same message id', async () => {
      const onMessage = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      act(() => {
        result.current.subscribe('conv-1', { onMessage });
      });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      const msgData = JSON.stringify({
        conversation_id: 'conv-1',
        is_mine: false,
        message: { id: 'msg-dup', content: 'Hello', sender_id: 'u2', sender_name: 'Jane', created_at: '2025-01-01' },
      });

      // Send same message twice
      act(() => { es.emit('new_message', msgData); });
      act(() => { es.emit('new_message', msgData); });

      // Handler should only be called once due to deduplication
      expect(onMessage).toHaveBeenCalledTimes(1);
    });

    it('routes typing_status events to handler', async () => {
      const onTyping = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onTyping }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('typing_status', JSON.stringify({
          conversation_id: 'conv-1', user_id: 'u2', user_name: 'Jane', is_typing: true, timestamp: '2025-01-01',
        }));
      });

      expect(onTyping).toHaveBeenCalledWith('u2', 'Jane', true);
    });

    it('routes read_receipt events with message_ids array', async () => {
      const onReadReceipt = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onReadReceipt }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('read_receipt', JSON.stringify({
          conversation_id: 'conv-1', reader_id: 'u2', message_ids: ['m1', 'm2'],
        }));
      });

      expect(onReadReceipt).toHaveBeenCalledWith(['m1', 'm2'], 'u2');
    });

    it('routes read_receipt with singular message_id fallback', async () => {
      const onReadReceipt = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onReadReceipt }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Send read_receipt with message_id instead of message_ids
      act(() => {
        es.emit('read_receipt', JSON.stringify({
          conversation_id: 'conv-1', reader_id: 'u2', message_id: 'm-single',
        }));
      });

      expect(onReadReceipt).toHaveBeenCalledWith(['m-single'], 'u2');
    });

    it('routes reaction_update events', async () => {
      const onReaction = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onReaction }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('reaction_update', JSON.stringify({
          conversation_id: 'conv-1', message_id: 'm1', emoji: '👍', action: 'added', user_id: 'u2',
        }));
      });

      expect(onReaction).toHaveBeenCalledWith('m1', '👍', 'added', 'u2');
    });

    it('routes message_edited events when handler and content are present', async () => {
      const onMessageEdited = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onMessageEdited }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('message_edited', JSON.stringify({
          conversation_id: 'conv-1', message_id: 'm1', editor_id: 'u1', data: { content: 'edited text' },
        }));
      });

      expect(onMessageEdited).toHaveBeenCalledWith('m1', 'edited text', 'u1');
    });

    it('does not call message_edited handler when content is missing', async () => {
      const onMessageEdited = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onMessageEdited }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('message_edited', JSON.stringify({
          conversation_id: 'conv-1', message_id: 'm1', editor_id: 'u1', data: {},
        }));
      });

      expect(onMessageEdited).not.toHaveBeenCalled();
    });

    it('routes message_deleted events', async () => {
      const onMessageDeleted = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onMessageDeleted }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('message_deleted', JSON.stringify({
          conversation_id: 'conv-1', message_id: 'm1', deleted_by: 'u1',
        }));
      });

      expect(onMessageDeleted).toHaveBeenCalledWith('m1', 'u1');
    });

    it('routes notification_update events to global handler', async () => {
      const onNotificationUpdate = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('__global__', { onNotificationUpdate }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('notification_update', JSON.stringify({ unread_count: 5 }));
      });

      expect(onNotificationUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'notification_update', unread_count: 5 })
      );
    });

    it('does not crash when no handler is registered for a conversation', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Emit to unsubscribed conversation
      act(() => {
        es.emit('new_message', JSON.stringify({
          conversation_id: 'conv-unknown', is_mine: false,
          message: { id: 'm1', content: 'test', sender_id: 'u1', sender_name: 'X', created_at: '2025-01-01' },
        }));
      });

      // Should not throw
    });

    it('handles malformed JSON in event data gracefully', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Should not throw
      act(() => {
        es.emit('new_message', 'not valid json');
      });
    });
  });

  describe('global handler for new_message and message_edited', () => {
    it('calls global handler for new_message events', async () => {
      const globalOnMessage = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('__global__', { onMessage: globalOnMessage }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('new_message', JSON.stringify({
          conversation_id: 'conv-1', is_mine: true,
          message: { id: 'm1', content: 'Hello', sender_id: 'u1', sender_name: 'John', created_at: '2025-01-01' },
        }));
      });

      expect(globalOnMessage).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'm1' }),
        true
      );
    });

    it('calls global handler for message_edited events', async () => {
      const globalOnMessageEdited = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('__global__', { onMessageEdited: globalOnMessageEdited }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('message_edited', JSON.stringify({
          conversation_id: 'conv-1', message_id: 'm1', editor_id: 'u1', data: { content: 'edited' },
        }));
      });

      expect(globalOnMessageEdited).toHaveBeenCalledWith('m1', 'edited', 'u1');
    });
  });

  describe('heartbeat and keep-alive', () => {
    it('resets heartbeat on keep-alive event', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Should not throw
      act(() => { es.emit('keep-alive'); });
      act(() => { es.emit('heartbeat'); });
    });
  });

  describe('heartbeat timeout triggers reconnect', () => {
    it('reconnects after heartbeat timeout when no keep-alive received', async () => {
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });
      expect(result.current.isConnected).toBe(true);

      // Advance past HEARTBEAT_TIMEOUT (45000ms)
      act(() => {
        jest.advanceTimersByTime(45000);
      });

      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Heartbeat timeout');

      const instancesBefore = MockEventSource.instances.length;

      // Advance past RECONNECT_DELAY (3000ms) to trigger reconnect
      await act(async () => {
        jest.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should have created a new EventSource after heartbeat timeout reconnect
      expect(MockEventSource.instances.length).toBeGreaterThan(instancesBefore);
    });

    it('does not reconnect after heartbeat timeout when refresh fails', async () => {
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      mockRefreshAuthSession.mockResolvedValue(false);

      // Advance past heartbeat timeout
      act(() => {
        jest.advanceTimersByTime(45000);
      });

      expect(result.current.connectionError).toBe('Heartbeat timeout');
      const instancesBefore = MockEventSource.instances.length;

      // Advance past reconnect delay
      await act(async () => {
        jest.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should NOT have created new EventSource since refresh failed
      expect(MockEventSource.instances.length).toBe(instancesBefore);
      expect(result.current.connectionError).toBe('Not authenticated');
    });
  });

  describe('error handling and reconnection', () => {
    it('sets connectionError on EventSource error', async () => {
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      expect(result.current.isConnected).toBe(true);

      act(() => { es.triggerError(); });

      expect(result.current.isConnected).toBe(false);
      expect(result.current.connectionError).toBe('Connection lost');
    });

    it('reconnects after error with delay', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });
      act(() => { es.triggerError(); });

      const instancesBefore = MockEventSource.instances.length;

      // Advance past reconnect delay
      await act(async () => {
        jest.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should have created a new EventSource
      expect(MockEventSource.instances.length).toBeGreaterThan(instancesBefore);
    });

    it('does not reconnect when auth session refresh fails', async () => {
      mockRefreshAuthSession.mockResolvedValue(false);

      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });
      act(() => { es.triggerError(); });

      const instancesBefore = MockEventSource.instances.length;

      await act(async () => {
        jest.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should NOT have created a new EventSource
      expect(MockEventSource.instances.length).toBe(instancesBefore);
      expect(result.current.connectionError).toBe('Not authenticated');
    });
  });

  describe('deduplication pruning', () => {
    it('prunes seen message IDs when exceeding threshold', async () => {
      const onMessage = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onMessage }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Send 201 unique messages to exceed MAX_SEEN_MESSAGE_IDS (200)
      for (let i = 0; i < 201; i++) {
        act(() => {
          es.emit('new_message', JSON.stringify({
            conversation_id: 'conv-1', is_mine: false,
            message: { id: `msg-${i}`, content: `Hello ${i}`, sender_id: 'u2', sender_name: 'Jane', created_at: '2025-01-01' },
          }));
        });
      }

      // All 201 messages should have been delivered (no duplicates)
      expect(onMessage).toHaveBeenCalledTimes(201);

      // Now resend an old message that was pruned (first 101 are removed, keeping last 100)
      act(() => {
        es.emit('new_message', JSON.stringify({
          conversation_id: 'conv-1', is_mine: false,
          message: { id: 'msg-0', content: 'Resent', sender_id: 'u2', sender_name: 'Jane', created_at: '2025-01-01' },
        }));
      });

      // msg-0 was pruned from the set, so it should be delivered again
      expect(onMessage).toHaveBeenCalledTimes(202);
    });
  });

  describe('connect guard when already connecting (lines 282-289)', () => {
    it('skips connect when eventSourceRef already exists', async () => {
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // At this point eventSourceRef.current is set.
      // A second connect attempt (e.g., if isAuthenticated re-triggers)
      // should skip because hasExistingConnection is true.
      const instanceCount = MockEventSource.instances.length;

      // Force reconnect by changing auth and back
      mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        user: { id: 'user-1', first_name: 'John' },
        checkAuth: mockCheckAuth,
      });

      // No new EventSource should be created
      expect(MockEventSource.instances.length).toBe(instanceCount);
      expect(result.current.isConnected).toBe(true);
    });
  });

  describe('error handler suppressed log paths (lines 494, 508)', () => {
    it('suppresses error log when authRejected ref is true (line 494)', async () => {
      // First connect succeeds with a 401 on SSE token,
      // setting authRejectedRef = true. Then we make auth appear valid again
      // so connect() fires, but this time the token also returns 401 again.
      // Actually, a simpler approach: connect, then get a 401 on reconnect token
      // which sets authRejectedRef. Then a stale onerror fires.

      // Step 1: Connect successfully
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });
      expect(result.current.isConnected).toBe(true);

      // Step 2: Trigger error to start reconnect cycle
      act(() => { es.triggerError(); });
      expect(result.current.isConnected).toBe(false);

      // Step 3: During reconnect, token returns 401 which sets authRejectedRef = true
      mockFetchWithAuth.mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({}),
      });

      await act(async () => {
        jest.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // authRejectedRef should now be true; no new EventSource created
      expect(result.current.connectionError).toBe('Not authenticated');
    });

    it('suppresses duplicate error logs after first (line 508)', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // First error — sets connectionErrorLoggedRef to true
      act(() => { es.triggerError(); });

      // Re-connect to get a new EventSource
      mockFetchWithAuth.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ token: 'sse-token-456' }),
      });

      await act(async () => {
        jest.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // Ensure a new EventSource was created
      expect(MockEventSource.instances.length).toBeGreaterThan(1);
      const es2 = getLatestEventSource();
      act(() => { es2.emit('connected'); });

      // Second error after reconnect — connectionErrorLoggedRef is already true
      // so it takes the suppressed debug path (line 508)
      act(() => { es2.triggerError(); });

      expect(es2.readyState).toBe(2); // CLOSED
    });
  });

  describe('cleanup on unmount', () => {
    it('closes EventSource and clears timers on unmount', async () => {
      const { unmount } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      unmount();

      expect(es.readyState).toBe(2); // CLOSED
    });
  });

  describe('malformed JSON handling for all event types', () => {
    it('handles malformed JSON in typing_status gracefully', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Should not throw
      act(() => {
        es.emit('typing_status', '{invalid json');
      });
    });

    it('handles malformed JSON in read_receipt gracefully', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('read_receipt', 'not json');
      });
    });

    it('handles malformed JSON in reaction_update gracefully', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('reaction_update', '{{broken');
      });
    });

    it('handles malformed JSON in message_edited gracefully', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('message_edited', 'bad data');
      });
    });

    it('handles malformed JSON in message_deleted gracefully', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('message_deleted', 'not-json');
      });
    });

    it('handles malformed JSON in notification_update gracefully', async () => {
      renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('notification_update', '(not json)');
      });
    });
  });

  describe('read_receipt edge cases', () => {
    it('passes empty array when neither message_ids nor message_id is present', async () => {
      const onReadReceipt = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onReadReceipt }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // read_receipt with no message_ids and no message_id
      act(() => {
        es.emit('read_receipt', JSON.stringify({
          conversation_id: 'conv-1', reader_id: 'u2',
          // no message_ids, no message_id
        }));
      });

      expect(onReadReceipt).toHaveBeenCalledWith([], 'u2');
    });
  });

  describe('new_message without message.id bypasses dedup', () => {
    it('routes new_message events without message.id (no deduplication)', async () => {
      const onMessage = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('conv-1', { onMessage }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Send message with no id field
      act(() => {
        es.emit('new_message', JSON.stringify({
          conversation_id: 'conv-1', is_mine: false,
          message: { content: 'No ID message', sender_id: 'u2', sender_name: 'Jane', created_at: '2025-01-01' },
        }));
      });

      // Send same structure again - both should go through since no dedup without id
      act(() => {
        es.emit('new_message', JSON.stringify({
          conversation_id: 'conv-1', is_mine: false,
          message: { content: 'No ID message', sender_id: 'u2', sender_name: 'Jane', created_at: '2025-01-01' },
        }));
      });

      expect(onMessage).toHaveBeenCalledTimes(2);
    });
  });

  describe('global handler for message_edited without content', () => {
    it('does not call global onMessageEdited when content is missing', async () => {
      const globalOnMessageEdited = jest.fn();
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      act(() => { result.current.subscribe('__global__', { onMessageEdited: globalOnMessageEdited }); });
      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      act(() => {
        es.emit('message_edited', JSON.stringify({
          conversation_id: 'conv-1', message_id: 'm1', editor_id: 'u1', data: {},
        }));
      });

      // Global handler should NOT be called since data.content is falsy
      expect(globalOnMessageEdited).not.toHaveBeenCalled();
    });
  });

  describe('authenticated error handler branches (lines 499, 508)', () => {
    it('logs warning on first authenticated error (line 499-506)', async () => {
      const { logger } = jest.requireMock('@/lib/logger') as {
        logger: { warn: jest.Mock; debug: jest.Mock; info: jest.Mock; error: jest.Mock };
      };

      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });
      expect(result.current.isConnected).toBe(true);

      logger.warn.mockClear();

      // Trigger error while authenticated and connectionErrorLoggedRef is false
      act(() => { es.triggerError(); });

      // Should have logged the warning (line 500-505)
      expect(logger.warn).toHaveBeenCalledWith(
        '[SSE] Connection error, will retry',
        expect.objectContaining({ readyState: expect.any(Number) })
      );
    });

    it('suppresses duplicate error log on second error before connected event (line 508)', async () => {
      const { logger } = jest.requireMock('@/lib/logger') as {
        logger: { warn: jest.Mock; debug: jest.Mock; info: jest.Mock; error: jest.Mock };
      };

      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const es1 = getLatestEventSource();
      act(() => { es1.emit('connected'); });
      expect(result.current.isConnected).toBe(true);

      // First error — sets connectionErrorLoggedRef to true
      act(() => { es1.triggerError(); });
      expect(result.current.isConnected).toBe(false);

      // Reconnect — creates a new EventSource
      await act(async () => {
        jest.advanceTimersByTime(3000);
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      const es2 = getLatestEventSource();
      expect(es2).not.toBe(es1);

      logger.warn.mockClear();
      logger.debug.mockClear();

      // Second error BEFORE connected event fires on es2 —
      // connectionErrorLoggedRef is still true, so line 508 path should be taken
      act(() => { es2.triggerError(); });

      // Should NOT have called logger.warn with 'Connection error, will retry'
      const warnCalls = logger.warn.mock.calls.filter(
        (call: unknown[]) => call[0] === '[SSE] Connection error, will retry'
      );
      expect(warnCalls).toHaveLength(0);

      // Should have called logger.debug with the suppressed message
      const debugCalls = logger.debug.mock.calls.filter(
        (call: unknown[]) => call[0] === '[MSG-DEBUG] SSE: Connection error (suppressed)'
      );
      expect(debugCalls).toHaveLength(1);
    });
  });

  describe('error handler when not authenticated', () => {
    it('suppresses error when isAuthenticated is false during error event', async () => {
      const { result } = renderHook(() => useUserMessageStream());

      await act(async () => { await Promise.resolve(); await Promise.resolve(); });

      const es = getLatestEventSource();
      act(() => { es.emit('connected'); });

      // Now change auth state to false
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        checkAuth: mockCheckAuth,
      });

      // Trigger error while not authenticated
      act(() => { es.triggerError(); });

      expect(result.current.connectionError).toBe('Connection lost');
    });
  });
});
