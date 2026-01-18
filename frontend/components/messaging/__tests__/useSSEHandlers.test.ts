import { renderHook, act } from '@testing-library/react';
import { useSSEHandlers } from '../hooks/useSSEHandlers';

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('useSSEHandlers', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('initial state', () => {
    it('returns null typingStatus initially', () => {
      const { result } = renderHook(() => useSSEHandlers());

      expect(result.current.typingStatus).toBeNull();
    });

    it('returns empty sseReadReceipts initially', () => {
      const { result } = renderHook(() => useSSEHandlers());

      expect(result.current.sseReadReceipts).toEqual({});
    });

    it('returns handleSSETyping function', () => {
      const { result } = renderHook(() => useSSEHandlers());

      expect(typeof result.current.handleSSETyping).toBe('function');
    });

    it('returns handleSSEReadReceipt function', () => {
      const { result } = renderHook(() => useSSEHandlers());

      expect(typeof result.current.handleSSEReadReceipt).toBe('function');
    });
  });

  describe('handleSSETyping', () => {
    it('sets typing status when isTyping is true', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      expect(result.current.typingStatus).toEqual(
        expect.objectContaining({
          userId: 'user-1',
          userName: 'John Doe',
        })
      );
    });

    it('clears typing status when isTyping is false', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      expect(result.current.typingStatus).not.toBeNull();

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', false);
      });

      expect(result.current.typingStatus).toBeNull();
    });

    it('auto-clears typing status after timeout', () => {
      const { result } = renderHook(() => useSSEHandlers({ typingTimeoutMs: 3000 }));

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      expect(result.current.typingStatus).not.toBeNull();

      act(() => {
        jest.advanceTimersByTime(3000);
      });

      expect(result.current.typingStatus).toBeNull();
    });

    it('uses custom timeout when provided', () => {
      const { result } = renderHook(() => useSSEHandlers({ typingTimeoutMs: 5000 }));

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      act(() => {
        jest.advanceTimersByTime(3000);
      });

      expect(result.current.typingStatus).not.toBeNull();

      act(() => {
        jest.advanceTimersByTime(2000);
      });

      expect(result.current.typingStatus).toBeNull();
    });

    it('resets timeout when new typing event received', () => {
      const { result } = renderHook(() => useSSEHandlers({ typingTimeoutMs: 3000 }));

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      act(() => {
        jest.advanceTimersByTime(2000);
      });

      expect(result.current.typingStatus).not.toBeNull();

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      act(() => {
        jest.advanceTimersByTime(2000);
      });

      expect(result.current.typingStatus).not.toBeNull();

      act(() => {
        jest.advanceTimersByTime(1000);
      });

      expect(result.current.typingStatus).toBeNull();
    });

    it('includes until timestamp in typing status', () => {
      const now = Date.now();
      jest.setSystemTime(now);

      const { result } = renderHook(() => useSSEHandlers({ typingTimeoutMs: 3000 }));

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      expect(result.current.typingStatus?.until).toBe(now + 3000);
    });
  });

  describe('handleSSEReadReceipt', () => {
    it('adds read receipt for single message', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt(['msg-1'], 'user-1');
      });

      expect(result.current.sseReadReceipts['msg-1']).toBeDefined();
      expect(result.current.sseReadReceipts['msg-1']?.length).toBe(1);
      expect(result.current.sseReadReceipts['msg-1']?.[0]?.user_id).toBe('user-1');
    });

    it('adds read receipts for multiple messages', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt(['msg-1', 'msg-2', 'msg-3'], 'user-1');
      });

      expect(result.current.sseReadReceipts['msg-1']).toBeDefined();
      expect(result.current.sseReadReceipts['msg-2']).toBeDefined();
      expect(result.current.sseReadReceipts['msg-3']).toBeDefined();
    });

    it('does not duplicate receipts for same user', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt(['msg-1'], 'user-1');
      });

      act(() => {
        result.current.handleSSEReadReceipt(['msg-1'], 'user-1');
      });

      expect(result.current.sseReadReceipts['msg-1']?.length).toBe(1);
    });

    it('allows multiple users to have receipts for same message', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt(['msg-1'], 'user-1');
      });

      act(() => {
        result.current.handleSSEReadReceipt(['msg-1'], 'user-2');
      });

      expect(result.current.sseReadReceipts['msg-1']?.length).toBe(2);
    });

    it('includes read_at timestamp', () => {
      const now = new Date('2024-01-15T12:00:00Z');
      jest.setSystemTime(now);

      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt(['msg-1'], 'user-1');
      });

      expect(result.current.sseReadReceipts['msg-1']?.[0]?.read_at).toBe(
        now.toISOString()
      );
    });

    it('handles undefined messageIds gracefully', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt(
          undefined as unknown as string[],
          'user-1'
        );
      });

      expect(result.current.sseReadReceipts).toEqual({});
    });

    it('handles null messageIds gracefully', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt(null as unknown as string[], 'user-1');
      });

      expect(result.current.sseReadReceipts).toEqual({});
    });

    it('handles non-array messageIds gracefully', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt('msg-1' as unknown as string[], 'user-1');
      });

      expect(result.current.sseReadReceipts).toEqual({});
    });

    it('handles empty array messageIds', () => {
      const { result } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSEReadReceipt([], 'user-1');
      });

      expect(result.current.sseReadReceipts).toEqual({});
    });
  });

  describe('cleanup', () => {
    it('cleans up timeout on unmount', () => {
      const { result, unmount } = renderHook(() => useSSEHandlers());

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      expect(result.current.typingStatus).not.toBeNull();

      unmount();

      // Should not throw or cause issues
      act(() => {
        jest.advanceTimersByTime(5000);
      });
    });
  });

  describe('debug mode', () => {
    it('logs debug messages when debug is true', () => {
      const { logger } = jest.requireMock('@/lib/logger');
      const { result } = renderHook(() => useSSEHandlers({ debug: true }));

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      expect(logger.debug).toHaveBeenCalled();
    });

    it('does not log debug messages when debug is false', () => {
      const { logger } = jest.requireMock('@/lib/logger');
      const { result } = renderHook(() => useSSEHandlers({ debug: false }));

      act(() => {
        result.current.handleSSETyping('user-1', 'John Doe', true);
      });

      expect(logger.debug).not.toHaveBeenCalled();
    });
  });
});
