import { useState, useRef, useCallback, useEffect } from 'react';
import { logger } from '@/lib/logger';

/**
 * Typing status from SSE event
 */
export interface TypingStatus {
  userId: string;
  userName: string;
  until: number;
}

/**
 * Read receipt entry from SSE event
 */
export interface SSEReadReceiptEntry {
  user_id: string;
  read_at: string;
}

/**
 * Map of message_id -> array of read receipts
 */
export type SSEReadReceiptMap = Record<string, SSEReadReceiptEntry[]>;

/**
 * Parameters for useSSEHandlers hook
 */
export interface UseSSEHandlersParams {
  /** Timeout duration for typing indicator in milliseconds (default: 3000) */
  typingTimeoutMs?: number;
  /** Enable debug logging */
  debug?: boolean;
}

/**
 * Return type for useSSEHandlers hook
 */
export interface UseSSEHandlersReturn {
  /** Current typing status from SSE */
  typingStatus: TypingStatus | null;
  /** Map of message_id -> read receipts from SSE */
  sseReadReceipts: SSEReadReceiptMap;
  /** Handler for SSE typing events - pass to subscribe() */
  handleSSETyping: (userId: string, userName: string, isTyping: boolean) => void;
  /** Handler for SSE read receipt events - pass to subscribe() */
  handleSSEReadReceipt: (messageIds: string[], readerId: string) => void;
}

/**
 * Shared hook for handling SSE typing and read receipt events.
 * Manages state and cleanup for typing indicator timeout.
 *
 * @example
 * ```tsx
 * const { typingStatus, sseReadReceipts, handleSSETyping, handleSSEReadReceipt } = useSSEHandlers();
 *
 * // In SSE subscription
 * subscribe(bookingId, {
 *   onTyping: handleSSETyping,
 *   onReadReceipt: handleSSEReadReceipt,
 *   // ... other handlers
 * });
 *
 * // Use typingStatus for UI
 * {typingStatus && <span>{typingStatus.userName} is typing...</span>}
 * ```
 */
export function useSSEHandlers(params: UseSSEHandlersParams = {}): UseSSEHandlersReturn {
  const { typingTimeoutMs = 3000, debug = false } = params;

  const [typingStatus, setTypingStatus] = useState<TypingStatus | null>(null);
  const [sseReadReceipts, setSSEReadReceipts] = useState<SSEReadReceiptMap>({});
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
    };
  }, []);

  const handleSSETyping = useCallback(
    (userId: string, userName: string, isTyping: boolean) => {
      if (debug) {
        logger.debug('[useSSEHandlers] handleSSETyping', { userId, userName, isTyping });
      }

      if (isTyping) {
        setTypingStatus({ userId, userName, until: Date.now() + typingTimeoutMs });
        // Clear typing after timeout if no update
        if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
        typingTimeoutRef.current = setTimeout(() => setTypingStatus(null), typingTimeoutMs);
      } else {
        setTypingStatus(null);
      }
    },
    [typingTimeoutMs, debug]
  );

  const handleSSEReadReceipt = useCallback(
    (messageIds: string[], readerId: string) => {
      // Defensive check: SSE event might send undefined
      if (!messageIds || !Array.isArray(messageIds)) {
        if (debug) {
          logger.warn('[useSSEHandlers] Invalid read receipt event', { messageIds, readerId });
        }
        return;
      }

      if (debug) {
        logger.debug('[useSSEHandlers] handleSSEReadReceipt', { messageIds, readerId });
      }

      setSSEReadReceipts((prev) => {
        const updated = { ...prev };
        messageIds.forEach((msgId) => {
          const existing = updated[msgId] || [];
          if (!existing.find((r) => r.user_id === readerId)) {
            updated[msgId] = [...existing, { user_id: readerId, read_at: new Date().toISOString() }];
          }
        });
        return updated;
      });
    },
    [debug]
  );

  return {
    typingStatus,
    sseReadReceipts,
    handleSSETyping,
    handleSSEReadReceipt,
  };
}
