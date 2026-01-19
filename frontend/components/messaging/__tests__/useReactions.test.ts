import { renderHook, act, waitFor } from '@testing-library/react';
import { useReactions, type ReactionMutations, type ReactionMessage } from '../hooks/useReactions';

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('useReactions', () => {
  let mockMutations: ReactionMutations;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();

    mockMutations = {
      addReaction: jest.fn().mockResolvedValue({}),
      removeReaction: jest.fn().mockResolvedValue({}),
    };
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  const createMessage = (
    id: string,
    my_reactions: string[] = []
  ): ReactionMessage => ({
    id,
    my_reactions,
  });

  describe('initial state', () => {
    it('returns empty userReactions initially', () => {
      const { result } = renderHook(() =>
        useReactions({ messages: [], mutations: mockMutations })
      );

      expect(result.current.userReactions).toEqual({});
    });

    it('returns null processingReaction initially', () => {
      const { result } = renderHook(() =>
        useReactions({ messages: [], mutations: mockMutations })
      );

      expect(result.current.processingReaction).toBeNull();
    });

    it('initializes userReactions from messages with my_reactions', () => {
      const messages = [
        createMessage('msg-1', ['👍']),
        createMessage('msg-2', ['❤️']),
      ];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.userReactions['msg-1']).toBe('👍');
      expect(result.current.userReactions['msg-2']).toBe('❤️');
    });

    it('initializes with null for messages without reactions', () => {
      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.userReactions['msg-1']).toBeNull();
    });
  });

  describe('handleReaction - adding reactions', () => {
    it('adds reaction optimistically', async () => {
      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      expect(result.current.userReactions['msg-1']).toBe('👍');
    });

    it('calls addReaction mutation', async () => {
      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      expect(mockMutations.addReaction).toHaveBeenCalledWith({
        messageId: 'msg-1',
        data: { emoji: '👍' },
      });
    });

    it('reverts reaction on API failure', async () => {
      mockMutations.addReaction = jest.fn().mockRejectedValue(new Error('API Error'));

      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.userReactions['msg-1']).toBeNull();
    });
  });

  describe('handleReaction - removing reactions', () => {
    it('removes reaction when clicking same emoji', async () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // Wait for initialization
      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      expect(result.current.userReactions['msg-1']).toBeNull();
    });

    it('calls removeReaction mutation', async () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      expect(mockMutations.removeReaction).toHaveBeenCalledWith({
        messageId: 'msg-1',
        data: { emoji: '👍' },
      });
    });

    it('reverts on API failure when removing', async () => {
      mockMutations.removeReaction = jest.fn().mockRejectedValue(new Error('API Error'));

      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.userReactions['msg-1']).toBe('👍');
    });
  });

  describe('handleReaction - replacing reactions', () => {
    it('replaces reaction with different emoji', async () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '❤️');
      });

      expect(result.current.userReactions['msg-1']).toBe('❤️');
    });

    it('calls removeReaction then addReaction when replacing', async () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '❤️');
      });

      expect(mockMutations.removeReaction).toHaveBeenCalledWith({
        messageId: 'msg-1',
        data: { emoji: '👍' },
      });
      expect(mockMutations.addReaction).toHaveBeenCalledWith({
        messageId: 'msg-1',
        data: { emoji: '❤️' },
      });
    });

    it('reverts to original on remove failure during replace', async () => {
      mockMutations.removeReaction = jest.fn().mockRejectedValue(new Error('API Error'));

      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '❤️');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.userReactions['msg-1']).toBe('👍');
    });

    it('reverts to null on add failure during replace', async () => {
      mockMutations.addReaction = jest.fn().mockRejectedValue(new Error('API Error'));

      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '❤️');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.userReactions['msg-1']).toBeNull();
    });
  });

  describe('processing lock', () => {
    it('prevents multiple simultaneous reactions', async () => {
      const messages = [createMessage('msg-1', [])];

      let resolveFirst: () => void = () => {};
      mockMutations.addReaction = jest.fn().mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            resolveFirst = resolve;
          })
      );

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      act(() => {
        void result.current.handleReaction('msg-1', '👍');
      });

      act(() => {
        void result.current.handleReaction('msg-1', '❤️');
      });

      resolveFirst();

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(mockMutations.addReaction).toHaveBeenCalledTimes(1);
    });

    it('sets processingReaction while processing', async () => {
      const messages = [createMessage('msg-1', [])];

      let resolveAdd: () => void = () => {};
      mockMutations.addReaction = jest.fn().mockImplementation(
        () =>
          new Promise<void>((resolve) => {
            resolveAdd = resolve;
          })
      );

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      act(() => {
        void result.current.handleReaction('msg-1', '👍');
      });

      expect(result.current.processingReaction).toBe('msg-1');

      // Resolve the promise inside act to trigger the finally block
      await act(async () => {
        resolveAdd();
        // Wait for microtask queue to flush
        await Promise.resolve();
      });

      // Now advance timers to clear the processing lock timeout
      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.processingReaction).toBeNull();
    });
  });

  describe('hasReacted', () => {
    it('returns true when user has reacted with specific emoji', () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.hasReacted('msg-1', '👍')).toBe(true);
    });

    it('returns false when user has different reaction', () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.hasReacted('msg-1', '❤️')).toBe(false);
    });

    it('returns false when user has no reaction', () => {
      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.hasReacted('msg-1', '👍')).toBe(false);
    });

    it('uses local state over server state', async () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      expect(result.current.hasReacted('msg-1', '👍')).toBe(false);
    });
  });

  describe('getCurrentReaction', () => {
    it('returns current reaction emoji', () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.getCurrentReaction('msg-1')).toBe('👍');
    });

    it('returns null when no reaction', () => {
      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.getCurrentReaction('msg-1')).toBeNull();
    });

    it('uses local state over server state', async () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-1']).toBe('👍');
      });

      await act(async () => {
        await result.current.handleReaction('msg-1', '❤️');
      });

      expect(result.current.getCurrentReaction('msg-1')).toBe('❤️');
    });
  });

  describe('temporary message handling', () => {
    it('skips messages with IDs starting with "-"', async () => {
      const messages = [createMessage('-temp-123', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await act(async () => {
        await result.current.handleReaction('-temp-123', '👍');
      });

      expect(mockMutations.addReaction).not.toHaveBeenCalled();
    });
  });

  describe('onReactionComplete callback', () => {
    it('calls onReactionComplete after successful reaction', async () => {
      const messages = [createMessage('msg-1', [])];
      const onReactionComplete = jest.fn();

      const { result } = renderHook(() =>
        useReactions({
          messages,
          mutations: mockMutations,
          onReactionComplete,
        })
      );

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      expect(onReactionComplete).toHaveBeenCalled();
    });
  });

  describe('multiple reactions cleanup', () => {
    it('cleans up multiple reactions from server', async () => {
      const messages = [createMessage('msg-1', ['👍', '❤️', '😊'])];

      renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // Wait for cleanup async effect to complete
      await waitFor(() => {
        expect(mockMutations.removeReaction).toHaveBeenCalledWith({
          messageId: 'msg-1',
          data: { emoji: '❤️' },
        });
      });

      await waitFor(() => {
        expect(mockMutations.removeReaction).toHaveBeenCalledWith({
          messageId: 'msg-1',
          data: { emoji: '😊' },
        });
      });
    });
  });

  describe('message not found', () => {
    it('does nothing when message not found', async () => {
      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // Call handleReaction with non-existent message
      await act(async () => {
        if (result.current) {
          await result.current.handleReaction('msg-nonexistent', '👍');
        }
      });

      expect(mockMutations.addReaction).not.toHaveBeenCalled();
    });
  });

  describe('debug logging', () => {
    it('logs debug messages when debug is true', async () => {
      const { logger } = jest.requireMock('@/lib/logger');
      const messages = [createMessage('msg-1', [])];

      const { result } = renderHook(() =>
        useReactions({
          messages,
          mutations: mockMutations,
          debug: true,
        })
      );

      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(logger.debug).toHaveBeenCalled();
    });
  });

  describe('timeout cleanup', () => {
    it('clears existing processing timeout before setting new one', async () => {
      const messages = [createMessage('msg-1', []), createMessage('msg-2', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // First reaction
      await act(async () => {
        await result.current.handleReaction('msg-1', '👍');
      });

      // Advance timer partially
      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      // Now processingReaction should be null, start second reaction
      await act(async () => {
        await result.current.handleReaction('msg-2', '❤️');
      });

      // Advance past timeout
      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.processingReaction).toBeNull();
    });
  });

  describe('getCurrentReaction server fallback', () => {
    it('returns null for unknown message ID', () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // Query a message that doesn't exist
      expect(result.current.getCurrentReaction('msg-unknown')).toBeNull();
    });

    it('returns server reaction when not in local state', () => {
      const messages = [createMessage('msg-1', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // Before local state is set, it should still return the server value
      expect(result.current.getCurrentReaction('msg-1')).toBe('👍');
    });
  });
});
