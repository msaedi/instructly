import { useState, useEffect, useCallback, useRef } from 'react';
import { logger } from '@/lib/logger';

/**
 * Reaction state for a single message
 * Maps messageId -> emoji string or null (no reaction)
 */
export type UserReactionsMap = Record<string, string | null>;

/**
 * Mutation function signature for adding/removing reactions
 */
export interface ReactionMutations {
  addReaction: (params: { messageId: string; data: { emoji: string } }) => Promise<unknown>;
  removeReaction: (params: { messageId: string; data: { emoji: string } }) => Promise<unknown>;
}

/**
 * Message shape required by the hook
 * Must have id and optionally my_reactions array
 */
export interface ReactionMessage {
  id: string;
  my_reactions?: string[] | undefined;
}

export interface UseReactionsParams<T extends ReactionMessage> {
  /** Current list of messages */
  messages: T[];
  /** Mutation functions for API calls */
  mutations: ReactionMutations;
  /** Optional callback after successful reaction change (e.g., for cache invalidation) */
  onReactionComplete?: () => void;
  /** Enable verbose debug logging (default: false) */
  debug?: boolean;
}

export interface UseReactionsReturn {
  /** Map of messageId -> current user's emoji (or null) */
  userReactions: UserReactionsMap;
  /** MessageId currently being processed (null if idle) */
  processingReaction: string | null;
  /** Toggle a reaction on a message - handles add/remove/replace */
  handleReaction: (messageId: string, emoji: string) => Promise<void>;
  /** Check if user has reacted with a specific emoji */
  hasReacted: (messageId: string, emoji: string) => boolean;
  /** Get current user's reaction for a message (or null) */
  getCurrentReaction: (messageId: string) => string | null;
}

/**
 * Shared hook for managing message reactions across student and instructor views.
 *
 * Features:
 * - Single-emoji enforcement (users can only have one reaction per message)
 * - Optimistic UI updates with error rollback
 * - Processing lock to prevent double-clicks
 * - Automatic initialization from server state
 * - Multi-reaction cleanup (removes duplicates from server)
 */
export function useReactions<T extends ReactionMessage>({
  messages,
  mutations,
  onReactionComplete,
  debug = false,
}: UseReactionsParams<T>): UseReactionsReturn {
  const [userReactions, setUserReactions] = useState<UserReactionsMap>({});
  const [processingReaction, setProcessingReaction] = useState<string | null>(null);

  // Track cleanup to prevent duplicate cleanup calls
  const cleanupInProgressRef = useRef<Set<string>>(new Set());

  const log = useCallback(
    (message: string, data?: Record<string, unknown>) => {
      if (debug) {
        logger.debug(`[useReactions] ${message}`, data);
      }
    },
    [debug]
  );

  // Initialize userReactions from server data when messages load
  // Also clean up any multiple reactions (enforce single emoji per message)
  useEffect(() => {
    setUserReactions((prev) => {
      const updated: UserReactionsMap = { ...prev };
      let hasChanges = false;
      const cleanupNeeded: Array<{ messageId: string; keepEmoji: string; removeEmojis: string[] }> = [];

      messages.forEach((message) => {
        // Only initialize if not already in state
        if (!(message.id in updated)) {
          const myReactions = message.my_reactions || [];
          updated[message.id] = myReactions[0] ?? null;
          hasChanges = true;

          // If server has multiple reactions, schedule cleanup
          if (myReactions.length > 1 && !cleanupInProgressRef.current.has(message.id)) {
            cleanupNeeded.push({
              messageId: message.id,
              keepEmoji: myReactions[0] ?? '',
              removeEmojis: myReactions.slice(1),
            });
          }
        }
      });

      // Clean up multiple reactions asynchronously
      if (cleanupNeeded.length > 0) {
        void (async () => {
          for (const cleanup of cleanupNeeded) {
            if (cleanupInProgressRef.current.has(cleanup.messageId)) continue;
            cleanupInProgressRef.current.add(cleanup.messageId);

            for (const emojiToRemove of cleanup.removeEmojis) {
              try {
                await mutations.removeReaction({
                  messageId: cleanup.messageId,
                  data: { emoji: emojiToRemove },
                });
                log('Cleaned up extra reaction', { messageId: cleanup.messageId, emoji: emojiToRemove });
              } catch {
                // Silent fail - cleanup is best-effort
              }
            }
            cleanupInProgressRef.current.delete(cleanup.messageId);
          }
        })();
      }

      return hasChanges ? updated : prev;
    });
  }, [messages, mutations, log]);

  const handleReaction = useCallback(
    async (messageId: string, emoji: string) => {
      // Skip temporary/optimistic messages
      if (messageId.startsWith('-')) {
        log('Skipping temp message', { messageId });
        return;
      }

      // Prevent multiple simultaneous reactions
      if (processingReaction !== null) {
        log('Already processing, ignoring', { processingReaction, newRequest: { messageId, emoji } });
        return;
      }

      // Find the message
      const message = messages.find((m) => m.id === messageId);
      if (!message) {
        log('Message not found', { messageId });
        return;
      }

      try {
        setProcessingReaction(messageId);

        // Get current state - local state takes precedence over server
        const myReactions = message.my_reactions || [];
        const localReaction = userReactions[messageId];
        const currentReaction = localReaction !== undefined ? localReaction : (myReactions[0] ?? null);

        log('Current state', { messageId, emoji, currentReaction, serverReactions: myReactions });

        if (currentReaction && currentReaction !== emoji) {
          // REPLACE: User has a different reaction, swap it
          log('Replacing reaction', { from: currentReaction, to: emoji });

          // Optimistic update
          setUserReactions((prev) => ({ ...prev, [messageId]: emoji }));

          // Remove old reaction
          try {
            await mutations.removeReaction({ messageId, data: { emoji: currentReaction } });
          } catch {
            // Revert on failure
            setUserReactions((prev) => ({ ...prev, [messageId]: currentReaction }));
            return;
          }

          // Add new reaction
          try {
            await mutations.addReaction({ messageId, data: { emoji } });
          } catch {
            // Revert to no reaction (old one was removed)
            setUserReactions((prev) => ({ ...prev, [messageId]: null }));
            return;
          }
        } else if (currentReaction === emoji) {
          // TOGGLE OFF: User clicked same reaction, remove it
          log('Toggling off reaction', { emoji });

          // Optimistic update
          setUserReactions((prev) => ({ ...prev, [messageId]: null }));

          try {
            await mutations.removeReaction({ messageId, data: { emoji } });
          } catch {
            // Revert on failure
            setUserReactions((prev) => ({ ...prev, [messageId]: emoji }));
          }
        } else {
          // ADD: No current reaction, add new one
          log('Adding new reaction', { emoji });

          // Optimistic update
          setUserReactions((prev) => ({ ...prev, [messageId]: emoji }));

          try {
            await mutations.addReaction({ messageId, data: { emoji } });
          } catch {
            // Revert on failure
            setUserReactions((prev) => ({ ...prev, [messageId]: null }));
          }
        }

        // Notify caller of successful completion
        onReactionComplete?.();
      } finally {
        // Small delay before allowing new reactions to prevent race conditions
        setTimeout(() => {
          setProcessingReaction(null);
        }, 200);
      }
    },
    [processingReaction, messages, userReactions, mutations, onReactionComplete, log]
  );

  const hasReacted = useCallback(
    (messageId: string, emoji: string): boolean => {
      const localReaction = userReactions[messageId];
      if (localReaction !== undefined) {
        return localReaction === emoji;
      }
      // Fall back to server state
      const message = messages.find((m) => m.id === messageId);
      const myReactions = message?.my_reactions || [];
      return myReactions.length > 0 && myReactions[0] === emoji;
    },
    [userReactions, messages]
  );

  const getCurrentReaction = useCallback(
    (messageId: string): string | null => {
      const localReaction = userReactions[messageId];
      if (localReaction !== undefined) {
        return localReaction;
      }
      // Fall back to server state
      const message = messages.find((m) => m.id === messageId);
      return message?.my_reactions?.[0] ?? null;
    },
    [userReactions, messages]
  );

  return {
    userReactions,
    processingReaction,
    handleReaction,
    hasReacted,
    getCurrentReaction,
  };
}
