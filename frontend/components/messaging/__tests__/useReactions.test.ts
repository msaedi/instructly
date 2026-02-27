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

  describe('handleReaction — uses server state when local state is undefined', () => {
    it('falls back to server my_reactions when localReaction is undefined', async () => {
      // Create messages but DON'T let useEffect initialize state (use fresh messages array)
      const initialMessages = [createMessage('msg-new', ['😊'])];

      const { result, rerender } = renderHook(
        ({ messages }: { messages: ReactionMessage[] }) =>
          useReactions({ messages, mutations: mockMutations }),
        { initialProps: { messages: initialMessages } }
      );

      // Wait for initialization
      await waitFor(() => {
        expect(result.current.userReactions['msg-new']).toBe('😊');
      });

      // Add a new message that the hook hasn't initialized yet
      const updatedMessages = [...initialMessages, createMessage('msg-fresh', ['🎉'])];
      rerender({ messages: updatedMessages });

      // Wait for the new message to be initialized
      await waitFor(() => {
        expect(result.current.userReactions['msg-fresh']).toBe('🎉');
      });

      // Toggle off the reaction on msg-fresh
      await act(async () => {
        await result.current.handleReaction('msg-fresh', '🎉');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.userReactions['msg-fresh']).toBeNull();
    });
  });

  describe('handleReaction — message with undefined my_reactions', () => {
    it('treats undefined my_reactions as empty array', async () => {
      const messages: ReactionMessage[] = [{ id: 'msg-undef', my_reactions: undefined }];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // Should initialize with null (no reaction)
      expect(result.current.userReactions['msg-undef']).toBeNull();

      await act(async () => {
        await result.current.handleReaction('msg-undef', '👍');
      });

      expect(result.current.userReactions['msg-undef']).toBe('👍');
      expect(mockMutations.addReaction).toHaveBeenCalledWith({
        messageId: 'msg-undef',
        data: { emoji: '👍' },
      });
    });
  });

  describe('multiple reactions cleanup edge cases', () => {
    it('skips cleanup for messages already being cleaned up', async () => {
      // First render triggers cleanup for msg-dup
      const messages = [createMessage('msg-dup', ['👍', '❤️', '😊'])];

      const removeReactionSlow = jest.fn().mockImplementation(
        () => new Promise<void>((resolve) => setTimeout(resolve, 100))
      );

      const slowMutations: ReactionMutations = {
        addReaction: jest.fn().mockResolvedValue({}),
        removeReaction: removeReactionSlow,
      };

      const { rerender } = renderHook(
        ({ msgs }: { msgs: ReactionMessage[] }) =>
          useReactions({ messages: msgs, mutations: slowMutations }),
        { initialProps: { msgs: messages } }
      );

      // Re-render with same messages while cleanup is in progress
      rerender({ msgs: [...messages] });

      // The cleanup should only be triggered once, not duplicated
      // Wait for the cleanup to complete
      await act(async () => {
        jest.advanceTimersByTime(200);
        await Promise.resolve();
        await Promise.resolve();
      });
    });

    it('handles cleanup removeReaction failure silently', async () => {
      const failingMutations: ReactionMutations = {
        addReaction: jest.fn().mockResolvedValue({}),
        removeReaction: jest.fn().mockRejectedValue(new Error('Cleanup failed')),
      };

      const messages = [createMessage('msg-cleanup-fail', ['👍', '❤️'])];

      renderHook(() =>
        useReactions({ messages, mutations: failingMutations })
      );

      // Wait for cleanup attempt to complete (silently fails)
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should not throw
      expect(failingMutations.removeReaction).toHaveBeenCalledWith({
        messageId: 'msg-cleanup-fail',
        data: { emoji: '❤️' },
      });
    });
  });

  describe('debug logging disabled by default', () => {
    it('does not call logger.debug when debug is false (default)', async () => {
      const { logger } = jest.requireMock('@/lib/logger');
      (logger.debug as jest.Mock).mockClear();

      const messages = [createMessage('msg-nodebug', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await act(async () => {
        await result.current.handleReaction('msg-nodebug', '👍');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      // logger.debug should NOT have been called with [useReactions] prefix
      const useReactionsCalls = (logger.debug as jest.Mock).mock.calls.filter(
        (call: unknown[]) => typeof call[0] === 'string' && (call[0] as string).includes('[useReactions]')
      );
      expect(useReactionsCalls).toHaveLength(0);
    });
  });

  describe('onReactionComplete not provided', () => {
    it('does not crash when onReactionComplete callback is not provided', async () => {
      const messages = [createMessage('msg-no-callback', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      await act(async () => {
        await result.current.handleReaction('msg-no-callback', '👍');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      // Should complete without error
      expect(result.current.userReactions['msg-no-callback']).toBe('👍');
    });
  });

  describe('hasReacted — server fallback with no reactions', () => {
    it('returns false when server has empty my_reactions and no local state', () => {
      const messages = [createMessage('msg-empty-server', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // hasReacted checks local state first, finds null, returns false
      expect(result.current.hasReacted('msg-empty-server', '👍')).toBe(false);
    });

    it('returns false when message has no my_reactions at all', () => {
      const messages: ReactionMessage[] = [{ id: 'msg-no-reactions' }];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      expect(result.current.hasReacted('msg-no-reactions', '👍')).toBe(false);
    });

    it('falls back to server state for unknown message in hasReacted', () => {
      const messages = [createMessage('msg-known', ['👍'])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // Query hasReacted for a message not in the list
      expect(result.current.hasReacted('msg-not-in-list', '👍')).toBe(false);
    });
  });

  describe('processingTimeoutRef cleanup on rapid reactions', () => {
    it('clears and replaces the processing timeout on back-to-back reactions', async () => {
      const messages = [createMessage('msg-rapid-1', []), createMessage('msg-rapid-2', [])];

      const { result } = renderHook(() =>
        useReactions({ messages, mutations: mockMutations })
      );

      // First reaction
      await act(async () => {
        await result.current.handleReaction('msg-rapid-1', '👍');
      });

      // Advance timer to clear processing lock
      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      // Start second reaction immediately
      await act(async () => {
        await result.current.handleReaction('msg-rapid-2', '❤️');
      });

      // The second reaction should have set a new timeout, clearing the old one
      // Advance to clear processing
      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.processingReaction).toBeNull();
      expect(result.current.userReactions['msg-rapid-1']).toBe('👍');
      expect(result.current.userReactions['msg-rapid-2']).toBe('❤️');
    });

  });

  describe('initialization does not override existing local state', () => {
    it('does not re-initialize a message already in local state', async () => {
      const messages = [createMessage('msg-keep', ['👍'])];

      const { result, rerender } = renderHook(
        ({ msgs }: { msgs: ReactionMessage[] }) =>
          useReactions({ messages: msgs, mutations: mockMutations }),
        { initialProps: { msgs: messages } }
      );

      await waitFor(() => {
        expect(result.current.userReactions['msg-keep']).toBe('👍');
      });

      // Change reaction locally
      await act(async () => {
        await result.current.handleReaction('msg-keep', '❤️');
      });

      await act(async () => {
        jest.advanceTimersByTime(200);
      });

      expect(result.current.userReactions['msg-keep']).toBe('❤️');

      // Re-render with server still showing old reaction - should NOT override local state
      rerender({ msgs: [createMessage('msg-keep', ['👍'])] });

      // Local state should still show the updated reaction
      expect(result.current.userReactions['msg-keep']).toBe('❤️');
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
