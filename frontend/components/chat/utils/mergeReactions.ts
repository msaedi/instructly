/**
 * Pure function to merge local and server reactions for display.
 *
 * This handles optimistic updates by:
 * 1. Starting with server reaction counts
 * 2. Adjusting for any local reaction that differs from server state
 * 3. Applying any SSE-delivered reaction deltas
 */

export interface MergeReactionsInput {
  /** Server reaction counts: { "👍": 3, "❤️": 2 } */
  serverReactions: Record<string, number>;
  /** User's local reaction for this message (undefined = not set, null = removed, string = emoji) */
  localReaction: string | null | undefined;
  /** User's reaction according to server (undefined or the emoji) */
  serverUserReaction: string | undefined;
  /** Deltas from SSE: { "👍": 1, "❤️": -1 } */
  reactionDeltas?: Record<string, number> | undefined;
}

/**
 * Merges server reactions with local optimistic updates and SSE deltas.
 *
 * @param input - The input containing server state and local modifications
 * @returns Merged reaction counts for display
 */
export function mergeReactions(input: MergeReactionsInput): Record<string, number> {
  const { serverReactions, localReaction, serverUserReaction, reactionDeltas } = input;

  // Start with a copy of server reactions
  const displayReactions: Record<string, number> = { ...serverReactions };

  // Apply local optimistic update if it differs from server state
  if (localReaction !== undefined && localReaction !== serverUserReaction) {
    // Remove server reaction count if server says user had a different reaction
    if (serverUserReaction) {
      displayReactions[serverUserReaction] = Math.max(
        0,
        (displayReactions[serverUserReaction] || 0) - 1
      );
      if (displayReactions[serverUserReaction] === 0) {
        delete displayReactions[serverUserReaction];
      }
    }
    // Add local reaction count
    if (localReaction) {
      displayReactions[localReaction] = (displayReactions[localReaction] || 0) + 1;
    }
  }

  // Apply SSE deltas (incremental reaction changes from other users)
  if (reactionDeltas) {
    Object.entries(reactionDeltas).forEach(([emoji, change]) => {
      displayReactions[emoji] = Math.max(0, (displayReactions[emoji] || 0) + change);
      if (displayReactions[emoji] === 0) {
        delete displayReactions[emoji];
      }
    });
  }

  return displayReactions;
}
