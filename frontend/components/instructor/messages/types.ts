/**
 * Types for the Instructor Messages Page
 *
 * Consolidated type definitions for messaging components, hooks, and utilities.
 */

import type { MessageResponse } from '@/src/api/generated/instructly.schemas';

/**
 * Message attachment metadata
 */
export type MessageAttachment = {
  name: string;
  type: string;
  dataUrl: string;
};

/**
 * Simplified message item for UI rendering
 */
export type MessageItem = {
  id: string;
  text: string;
  sender: 'instructor' | 'student' | 'platform';
  timestamp: string;
};

/**
 * Read receipt entry from message response
 */
export type ReadByEntry = {
  user_id: string;
  read_at?: string | null;
};

/**
 * Message delivery status
 */
export type MessageDelivery =
  | { status: 'sending' }
  | { status: 'delivered'; timeLabel: string }
  | { status: 'read'; timeLabel: string };

/**
 * Extended message with attachments and delivery info
 */
export type MessageWithAttachments = MessageItem & {
  attachments?: MessageAttachment[] | undefined;
  delivery?: MessageDelivery | undefined;
  createdAt?: string | undefined;
  senderId?: string | undefined;
  isArchived?: boolean | undefined;
  isTrashed?: boolean | undefined;
};

/**
 * Conversation entry in the sidebar list
 */
export type ConversationEntry = {
  id: string;
  name: string;
  lastMessage: string;
  timestamp: string;
  unread: number;
  avatar: string;
  type: 'student' | 'platform';
  bookingIds: string[];
  primaryBookingId: string | null;
  studentId: string | null;
  instructorId: string | null;
  latestMessageAt: number;
  latestMessageId?: string | null;
};

/**
 * Template item for quick replies
 */
export type TemplateItem = {
  id: string;
  subject: string;
  preview: string;
  body: string;
};

/**
 * Thread history load state tracking
 */
export type ThreadHistoryMeta = {
  status: 'idle' | 'loading' | 'success' | 'error';
  lastMessageId: string | null;
  timestamp: number;
};

/**
 * Thread state snapshot for undo operations
 */
export type ThreadStateSnapshot = {
  active: MessageWithAttachments[];
  archived: MessageWithAttachments[];
  trash: MessageWithAttachments[];
};

/**
 * Filter option for conversation list
 */
export type FilterOption = {
  label: string;
  value: 'all' | 'student' | 'platform';
};

/**
 * Message display mode
 */
export type MessageDisplayMode = 'inbox' | 'archived' | 'trash';

/**
 * Mail section view
 */
export type MailSection = 'inbox' | 'compose' | 'sent' | 'drafts' | 'templates';

/**
 * SSE Message with ownership flag
 */
export type SSEMessageWithOwnership = MessageResponse & {
  is_mine?: boolean;
  sender_id?: string;
};
