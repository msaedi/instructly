/**
 * Message processing utilities
 */

import type { MessageResponse } from '@/src/api/generated/instructly.schemas';
import type { Booking } from '@/features/shared/api/types';
import type {
  ConversationEntry,
  MessageDelivery,
  MessageWithAttachments,
  ReadByEntry,
} from '../types';
import { formatRelativeTime, formatTimeLabel } from './formatters';

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
  message: MessageResponse,
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
    const readByEntries = (message.read_by ?? []) as ReadByEntry[];
    const recipientRead = recipientId
      ? readByEntries.find((entry) => entry.user_id === recipientId && entry.read_at)
      : undefined;
    if (recipientRead) {
      delivery = {
        status: 'read',
        timeLabel: formatTimeLabel(recipientRead.read_at ?? message.updated_at ?? message.created_at),
      };
    } else if (message.delivered_at) {
      delivery = { status: 'delivered', timeLabel: formatTimeLabel(message.delivered_at) };
    } else {
      delivery = { status: 'delivered', timeLabel: formatTimeLabel(message.created_at) };
    }
  }

  const isDeleted = Boolean((message as { is_deleted?: boolean }).is_deleted);
  const mapped: MessageWithAttachments = {
    id: message.id,
    text: isDeleted ? 'This message was deleted' : message.content ?? '',
    sender: senderType,
    timestamp: formatRelativeTime(message.created_at),
    isDeleted,
    deletedAt: (message as { deleted_at?: string | null }).deleted_at || undefined,
    deletedBy: (message as { deleted_by?: string | null }).deleted_by || undefined,
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
  if (typeof (message as { is_deleted?: unknown }).is_deleted === 'boolean') {
    mapped.isArchived = Boolean((message as { is_deleted?: boolean }).is_deleted);
  }

  // Preserve delivered_at and read_by from API response
  if (message.delivered_at) {
    mapped.delivered_at = message.delivered_at;
  }
  if (message.read_by) {
    mapped.read_by = message.read_by as ReadByEntry[];
  }

  return mapped;
};

/**
 * Compute unread count from messages for current user
 */
export const computeUnreadFromMessages = (
  messages: MessageResponse[] | undefined,
  conversation: ConversationEntry | undefined,
  currentUserId: string
): number => {
  if (!messages || !conversation) return 0;
  return messages.reduce((count, msg) => {
    if (msg.sender_id === currentUserId) return count;
    const readByEntries = (msg.read_by ?? []) as ReadByEntry[];
    const hasRead = readByEntries.some(
      (entry) => entry.user_id === currentUserId && !!entry.read_at
    );
    return hasRead ? count : count + 1;
  }, 0);
};
