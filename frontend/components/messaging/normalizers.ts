import type { MessageWithAttachments } from '@/components/instructor/messages/types';
import type { NormalizedMessage, NormalizedReaction, NormalizedAttachment } from './types';

// Minimal normalizers to convert student/instructor message shapes into NormalizedMessage.
// These helpers can be expanded as needed; current usage focuses on bubble rendering only.

/**
 * Check if a message type is a system message
 */
export function isSystemMessage(messageType: string | undefined | null): boolean {
  if (!messageType) return false;
  return messageType.startsWith('system_') || messageType === 'system';
}

export function normalizeStudentMessage(
  message: {
    id: string;
    content?: string | null;
    created_at: string;
    sender_id?: string | null;
    sender_name?: string | null;
    edited_at?: string | null;
    is_deleted?: boolean;
  },
  currentUserId: string,
  options?: {
    reactions?: NormalizedReaction[];
    currentUserReaction?: string | null;
    timestampLabel?: string;
    readStatus?: 'sent' | 'delivered' | 'read' | undefined;
    readTimestampLabel?: string | undefined;
  }
): NormalizedMessage {
  return {
    id: message.id,
    content: message.content ?? '',
    timestamp: new Date(message.created_at),
    timestampLabel: options?.timestampLabel ?? message.created_at,
    isOwn: message.sender_id === currentUserId,
    senderName: message.sender_name ?? undefined,
    isEdited: Boolean(message.edited_at),
    isDeleted: Boolean(message.is_deleted),
    readStatus: options?.readStatus ?? undefined,
    readTimestampLabel: options?.readTimestampLabel,
    reactions: options?.reactions ?? [],
    currentUserReaction: options?.currentUserReaction ?? null,
    _raw: message,
  };
}

export function normalizeInstructorMessage(
  message: MessageWithAttachments,
  currentUserId: string,
  options?: {
    reactions?: NormalizedReaction[];
    currentUserReaction?: string | null;
    timestampLabel?: string;
    readStatus?: 'sent' | 'delivered' | 'read' | undefined;
    readTimestampLabel?: string | undefined;
    attachments?: NormalizedAttachment[];
  }
): NormalizedMessage {
  return {
    id: message.id,
    content: message.text ?? '',
    timestamp: message.createdAt ? new Date(message.createdAt) : new Date(),
    timestampLabel: options?.timestampLabel ?? message.timestamp ?? '',
    isOwn: (message.senderId ?? message.sender) === currentUserId || message.sender === 'instructor',
    senderName: undefined,
    isEdited: Boolean(message.isEdited || message.editedAt),
    isDeleted: Boolean(message.isDeleted),
    readStatus: options?.readStatus ?? undefined,
    readTimestampLabel: options?.readTimestampLabel,
    reactions: options?.reactions ?? [],
    currentUserReaction: options?.currentUserReaction ?? null,
    attachments: options?.attachments,
    _raw: message,
  };
}
