import { mergeReactions, type MergeReactionsInput } from '../mergeReactions';

describe('mergeReactions', () => {
  describe('basic merging', () => {
    it('returns server reactions when no local changes', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 3, '❤️': 2 },
        localReaction: undefined,
        serverUserReaction: '👍',
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 3, '❤️': 2 });
    });

    it('returns empty object when no reactions exist', () => {
      const input: MergeReactionsInput = {
        serverReactions: {},
        localReaction: undefined,
        serverUserReaction: undefined,
      };

      const result = mergeReactions(input);

      expect(result).toEqual({});
    });

    it('preserves server reactions when local matches server', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 5 },
        localReaction: '👍',
        serverUserReaction: '👍',
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 5 });
    });
  });

  describe('optimistic updates', () => {
    it('adds local reaction when user adds new reaction', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 2 },
        localReaction: '❤️',
        serverUserReaction: undefined,
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 2, '❤️': 1 });
    });

    it('removes server reaction and adds local when user changes reaction', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 3, '❤️': 1 },
        localReaction: '❤️',
        serverUserReaction: '👍',
      };

      const result = mergeReactions(input);

      // Should decrement 👍 by 1 (user's old reaction) and increment ❤️ by 1
      expect(result).toEqual({ '👍': 2, '❤️': 2 });
    });

    it('removes reaction entirely when count becomes zero', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 1 },
        localReaction: '❤️',
        serverUserReaction: '👍',
      };

      const result = mergeReactions(input);

      // 👍 was 1, user removed it -> 0 -> deleted
      expect(result).toEqual({ '❤️': 1 });
      expect(result['👍']).toBeUndefined();
    });

    it('handles removing reaction (localReaction = null)', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 2 },
        localReaction: null,
        serverUserReaction: '👍',
      };

      const result = mergeReactions(input);

      // User removed their 👍, so decrement by 1
      expect(result).toEqual({ '👍': 1 });
    });

    it('removes reaction completely when user removes last one', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 1 },
        localReaction: null,
        serverUserReaction: '👍',
      };

      const result = mergeReactions(input);

      expect(result).toEqual({});
    });
  });

  describe('SSE reaction deltas', () => {
    it('applies positive deltas from SSE', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 2 },
        localReaction: undefined,
        serverUserReaction: undefined,
        reactionDeltas: { '👍': 1, '❤️': 2 },
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 3, '❤️': 2 });
    });

    it('applies negative deltas from SSE', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 5, '❤️': 3 },
        localReaction: undefined,
        serverUserReaction: undefined,
        reactionDeltas: { '👍': -2, '❤️': -1 },
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 3, '❤️': 2 });
    });

    it('removes reactions when delta brings count to zero', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 2, '❤️': 1 },
        localReaction: undefined,
        serverUserReaction: undefined,
        reactionDeltas: { '❤️': -1 },
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 2 });
      expect(result['❤️']).toBeUndefined();
    });

    it('clamps negative deltas at zero (no negative counts)', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 1 },
        localReaction: undefined,
        serverUserReaction: undefined,
        reactionDeltas: { '👍': -5 },
      };

      const result = mergeReactions(input);

      // Should be 0, then deleted
      expect(result).toEqual({});
    });
  });

  describe('combined local and SSE updates', () => {
    it('applies both local optimistic and SSE deltas', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 3 },
        localReaction: '❤️',
        serverUserReaction: '👍',
        reactionDeltas: { '👍': 2, '🔥': 1 },
      };

      const result = mergeReactions(input);

      // Start: 👍=3
      // Local change: 👍 -> ❤️, so 👍=2, ❤️=1
      // Deltas: 👍+2=4, 🔥=1
      expect(result).toEqual({ '👍': 4, '❤️': 1, '🔥': 1 });
    });

    it('handles complex scenario with all operations', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 5, '❤️': 2, '😂': 1 },
        localReaction: '🎉',
        serverUserReaction: '😂',
        reactionDeltas: { '👍': -1, '❤️': 3, '🔥': 2 },
      };

      const result = mergeReactions(input);

      // Start: 👍=5, ❤️=2, 😂=1
      // Local: 😂->🎉, so 😂=0 (deleted), 🎉=1
      // Deltas: 👍=5-1=4, ❤️=2+3=5, 🔥=2
      expect(result).toEqual({ '👍': 4, '❤️': 5, '🎉': 1, '🔥': 2 });
      expect(result['😂']).toBeUndefined();
    });
  });

  describe('edge cases', () => {
    it('handles empty deltas object', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 2 },
        localReaction: undefined,
        serverUserReaction: undefined,
        reactionDeltas: {},
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 2 });
    });

    it('handles undefined deltas', () => {
      const input: MergeReactionsInput = {
        serverReactions: { '👍': 2 },
        localReaction: undefined,
        serverUserReaction: undefined,
        reactionDeltas: undefined,
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 2 });
    });

    it('does not mutate input serverReactions', () => {
      const serverReactions = { '👍': 2 };
      const input: MergeReactionsInput = {
        serverReactions,
        localReaction: '❤️',
        serverUserReaction: undefined,
      };

      mergeReactions(input);

      // Original should be unchanged
      expect(serverReactions).toEqual({ '👍': 2 });
    });

    it('handles adding first reaction to message with no reactions', () => {
      const input: MergeReactionsInput = {
        serverReactions: {},
        localReaction: '👍',
        serverUserReaction: undefined,
      };

      const result = mergeReactions(input);

      expect(result).toEqual({ '👍': 1 });
    });

    it('handles serverUserReaction without matching serverReactions (inconsistent state)', () => {
      // Edge case: server says user reacted with 👍 but reaction count is missing
      const input: MergeReactionsInput = {
        serverReactions: {},
        localReaction: '❤️',
        serverUserReaction: '👍',
      };

      const result = mergeReactions(input);

      // Should try to decrement 👍 (clamped to 0, deleted) and add ❤️
      expect(result).toEqual({ '❤️': 1 });
    });
  });
});
