import { useMemo } from 'react';

/**
 * Standard read receipt entry shape (used by both message read_by and SSE events)
 */
export interface ReadReceiptEntry {
  user_id: string;
  read_at: string;
}

/**
 * Map of message ID -> array of read receipts
 */
export type ReadReceiptMap = Record<string, ReadReceiptEntry[]>;

/**
 * Minimal interface for messages - only requires an id.
 * All other fields are accessed via accessor functions for maximum flexibility.
 */
export interface ReadReceiptMessage {
  id: string;
}

export interface UseReadReceiptsParams<T extends ReadReceiptMessage> {
  /** Array of messages to process */
  messages: T[];
  /** SSE-delivered read receipts (real-time updates) */
  sseReadReceipts: ReadReceiptMap;
  /** Current user's ID */
  currentUserId: string;
  /** Function to extract read_by array from a message (returns array or null/undefined) */
  getReadBy: (message: T) => ReadReceiptEntry[] | null | undefined;
  /** Function to determine if a message was sent by the current user */
  isOwnMessage: (message: T) => boolean;
  /** Function to extract creation timestamp from a message */
  getCreatedAt: (message: T) => Date | null;
}

export interface UseReadReceiptsReturn {
  /** Merged read receipts from message data + SSE updates */
  mergedReadReceipts: ReadReceiptMap;
  /** ID of the last message sent by current user that has been read */
  lastReadMessageId: string | null;
  /** Check if a specific message has any read receipts */
  isMessageRead: (messageId: string) => boolean;
  /** Get the first read timestamp for a message (or null) */
  getReadAt: (messageId: string) => string | null;
}

/**
 * Shared hook for managing read receipts across student and instructor views.
 *
 * Features:
 * - Merges server-provided read_by with real-time SSE updates
 * - Deduplicates receipts by user_id + read_at
 * - Computes the last own message that was read (for "Read at X:XX" display)
 * - Provides helper functions for easy lookup
 *
 * @example Student side:
 * ```tsx
 * const { mergedReadReceipts, lastReadMessageId } = useReadReceipts({
 *   messages: allMessages,
 *   sseReadReceipts: readReceipts,
 *   currentUserId,
 *   getReadBy: (m) => m.read_by as ReadReceiptEntry[] | null | undefined,
 *   isOwnMessage: (m) => m.sender_id === currentUserId,
 *   getCreatedAt: (m) => new Date(m.created_at),
 * });
 * ```
 *
 * @example Instructor side:
 * ```tsx
 * const { mergedReadReceipts, lastReadMessageId } = useReadReceipts({
 *   messages: threadMessages,
 *   sseReadReceipts: readReceipts,
 *   currentUserId: currentUser?.id ?? '',
 *   getReadBy: (m) => m.read_by as ReadReceiptEntry[] | null | undefined,
 *   isOwnMessage: (m) => m.sender === 'instructor' || m.senderId === currentUser?.id,
 *   getCreatedAt: (m) => m.createdAt ? new Date(m.createdAt) : null,
 * });
 * ```
 */
export function useReadReceipts<T extends ReadReceiptMessage>({
  messages,
  sseReadReceipts,
  currentUserId,
  getReadBy,
  isOwnMessage,
  getCreatedAt,
}: UseReadReceiptsParams<T>): UseReadReceiptsReturn {
  // Merge read receipts from message data and SSE events
  const mergedReadReceipts = useMemo(() => {
    // Start with SSE receipts (real-time updates)
    const map: ReadReceiptMap = { ...sseReadReceipts };

    // Merge in receipts from message read_by field (server state)
    for (const message of messages) {
      const readBy = getReadBy(message);
      if (!readBy || !Array.isArray(readBy)) continue;

      const existing = map[message.id] || [];
      const combined = [...existing];

      for (const receipt of readBy) {
        // Skip if already have this exact receipt (same user + timestamp)
        const isDuplicate = combined.some(
          (x) => x.user_id === receipt.user_id && x.read_at === receipt.read_at
        );
        if (isDuplicate) continue;

        // Validate receipt has required fields
        if (receipt.user_id && receipt.read_at) {
          combined.push({ user_id: receipt.user_id, read_at: receipt.read_at });
        }
      }

      map[message.id] = combined;
    }

    return map;
  }, [messages, sseReadReceipts, getReadBy]);

  // Find the last own message that has been read (for "Read at X:XX" display)
  const lastReadMessageId = useMemo(() => {
    if (!currentUserId) return null;

    let latest: { id: string; timestamp: number } | null = null;

    for (const message of messages) {
      // Skip messages not sent by current user
      if (!isOwnMessage(message)) continue;

      // Skip messages without read receipts
      const receipts = mergedReadReceipts[message.id] || [];
      if (receipts.length === 0) continue;

      // Get creation timestamp
      const createdAt = getCreatedAt(message);
      if (!createdAt) continue;

      const timestamp = createdAt.getTime();
      if (Number.isNaN(timestamp)) continue;

      // Track the most recent
      if (!latest || timestamp > latest.timestamp) {
        latest = { id: message.id, timestamp };
      }
    }

    return latest?.id ?? null;
  }, [messages, mergedReadReceipts, currentUserId, isOwnMessage, getCreatedAt]);

  // Helper: check if message has any read receipts
  const isMessageRead = useMemo(() => {
    return (messageId: string): boolean => {
      const receipts = mergedReadReceipts[messageId];
      return !!receipts && receipts.length > 0;
    };
  }, [mergedReadReceipts]);

  // Helper: get first read timestamp for a message
  const getReadAt = useMemo(() => {
    return (messageId: string): string | null => {
      const receipts = mergedReadReceipts[messageId];
      return receipts?.[0]?.read_at ?? null;
    };
  }, [mergedReadReceipts]);

  return {
    mergedReadReceipts,
    lastReadMessageId,
    isMessageRead,
    getReadAt,
  };
}
