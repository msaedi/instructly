/**
 * Message processing utilities
 */

import type { Booking } from '@/features/shared/api/types';
import type {
  ConversationEntry,
  MessageDelivery,
  MessageWithAttachments,
  ReadByEntry,
} from '../types';
import { formatRelativeTimestamp, formatTimeLabel } from '@/components/messaging/formatters';

type MessageApiLike = {
  id: string;
  content?: string | null;
  sender_id?: string | null;
  created_at?: string;
  delivered_at?: string | null;
  read_by?: ReadByEntry[] | null;
  edited_at?: string | null;
  is_deleted?: boolean;
  reactions?: unknown;
  my_reactions?: string[] | null;
};

/**
 * Check if an error is an AbortError
 */
export const isAbortError = (error: unknown): boolean => {
  if (!error || typeof error !== 'object') return false;
  const name = (error as { name?: unknown }).name;
  return typeof name === 'string' && name === 'AbortError';
};

/**
 * Get the most relevant activity timestamp from a booking
 */
export const getBookingActivityTimestamp = (booking: Booking): string | undefined => {
  const possible = (booking as { updated_at?: string | null }).updated_at;
  return (
    possible ??
    booking.completed_at ??
    booking.confirmed_at ??
    booking.cancelled_at ??
    booking.created_at ??
    booking.booking_date ??
    undefined
  );
};

/**
 * Map a MessageResponse to MessageWithAttachments format
 */
export const mapMessageFromResponse = (
  message: MessageApiLike,
  conversation: ConversationEntry | undefined,
  currentUserId: string
): MessageWithAttachments => {
  const senderType: 'instructor' | 'student' | 'platform' =
    message.sender_id === currentUserId
      ? 'instructor'
      : conversation?.studentId && message.sender_id === conversation.studentId
        ? 'student'
        : conversation
          ? 'platform'
          : 'student';

  let delivery: MessageDelivery | undefined;
  if (senderType === 'instructor') {
    const recipientId = conversation?.studentId ?? null;
    const readByEntries = message.read_by ?? [];
    const recipientRead = recipientId
      ? readByEntries.find((entry) => entry.user_id === recipientId && entry.read_at)
      : undefined;
    if (recipientRead) {
      delivery = {
        status: 'read',
        timeLabel: formatTimeLabel(recipientRead.read_at ?? message.created_at ?? ''),
      };
    } else if (message.delivered_at) {
      delivery = { status: 'delivered', timeLabel: formatTimeLabel(message.delivered_at) };
    } else {
      delivery = { status: 'delivered', timeLabel: formatTimeLabel(message.created_at ?? '') };
    }
  }

  const isDeleted = Boolean(message.is_deleted);

  const reactionCounts: Record<string, number> | undefined = (() => {
    const raw = message.reactions;
    if (!raw) return undefined;

    if (Array.isArray(raw)) {
      const counts: Record<string, number> = {};
      for (const item of raw) {
        if (!item || typeof item !== 'object') continue;
        const emoji = (item as { emoji?: unknown }).emoji;
        if (typeof emoji !== 'string') continue;
        counts[emoji] = (counts[emoji] ?? 0) + 1;
      }
      return counts;
    }

    if (typeof raw === 'object') {
      return raw as Record<string, number>;
    }

    return undefined;
  })();

  const myReactions: string[] | undefined = (() => {
    const explicit = message.my_reactions;
    if (Array.isArray(explicit)) {
      return explicit.filter((x): x is string => typeof x === 'string');
    }

    const raw = message.reactions;
    if (!Array.isArray(raw)) return undefined;

    const mine: string[] = [];
    for (const item of raw) {
      if (!item || typeof item !== 'object') continue;
      const userId = (item as { user_id?: unknown }).user_id;
      const emoji = (item as { emoji?: unknown }).emoji;
      if (userId === currentUserId && typeof emoji === 'string') {
        mine.push(emoji);
      }
    }
    return mine;
  })();

  const mapped: MessageWithAttachments = {
    id: message.id,
    text: isDeleted ? 'This message was deleted' : message.content ?? '',
    sender: senderType,
    timestamp: formatRelativeTimestamp(message.created_at ?? ''),
    isDeleted,
    isEdited: Boolean(message.edited_at),
    editedAt: message.edited_at || undefined,
  };

  if (delivery) {
    mapped.delivery = delivery;
  }
  if (message.created_at) {
    mapped.createdAt = message.created_at;
  }
  if (message.sender_id) {
    mapped.senderId = message.sender_id;
  }
  if (message.edited_at) {
    mapped.editedAt = message.edited_at;
  }
  if (typeof message.is_deleted === 'boolean') {
    mapped.isArchived = message.is_deleted;
  }

  // Preserve delivered_at and read_by from API response
  if (message.delivered_at) {
    mapped.delivered_at = message.delivered_at;
  }
  if (message.read_by) {
    mapped.read_by = message.read_by as ReadByEntry[];
  }

  // Preserve reaction fields from API response
  if (reactionCounts) {
    mapped.reactions = reactionCounts;
  }
  if (myReactions) {
    mapped.my_reactions = myReactions;
  }

  return mapped;
};

/**
 * Compute unread count from messages for current user
 */
export const computeUnreadFromMessages = (
  messages: MessageApiLike[] | undefined,
  conversation: ConversationEntry | undefined,
  currentUserId: string
): number => {
  if (!messages || !conversation) return 0;
  return messages.reduce((count, msg) => {
    if (msg.sender_id === currentUserId) return count;
    const readByEntries = msg.read_by ?? [];
    const hasRead = readByEntries.some(
      (entry) => entry.user_id === currentUserId && !!entry.read_at
    );
    return hasRead ? count : count + 1;
  }, 0);
};
