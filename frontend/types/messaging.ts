// frontend/types/messaging.ts
/**
 * Types for real-time messaging via Server-Sent Events (SSE).
 *
 * Phase 4: Single user-scoped SSE connection for all conversations.
 * Events include conversation_id for client-side routing.
 */

export type SSEEventType =
  | 'new_message'
  | 'typing_status'
  | 'read_receipt'
  | 'reaction_update'
  | 'message_edited'
  | 'message_deleted';

export interface SSEMessageEvent {
  type: 'new_message';
  conversation_id: string; // PRIMARY key for SSE routing (Phase 7)
  booking_id?: string; // Optional context for which booking this message is about
  is_mine: boolean;
  message: {
    id: string;
    content: string;
    sender_id: string | null;
    sender_name: string | null;
    created_at: string;
    booking_id?: string;
    delivered_at?: string | null;
  };
}

export interface SSETypingEvent {
  type: 'typing_status';
  conversation_id: string;
  user_id: string;
  user_name: string;
  is_typing: boolean;
  timestamp: string;
}

export interface SSEReadReceiptEvent {
  type: 'read_receipt';
  conversation_id: string;
  reader_id: string;
  message_ids: string[];
}

export interface SSEReactionEvent {
  type: 'reaction_update';
  conversation_id: string;
  message_id: string;
  emoji: string;
  user_id: string;
  action: 'added' | 'removed';
}

export interface SSEMessageEditedEvent {
  type: 'message_edited';
  conversation_id: string;
  message_id: string;
  editor_id: string;
  data: {
    content: string;
  };
}

export interface SSEMessageDeletedEvent {
  type: 'message_deleted';
  conversation_id: string;
  message_id: string;
  deleted_by: string;
  deleted_at?: string;
}

export type SSEEvent =
  | SSEMessageEvent
  | SSETypingEvent
  | SSEReadReceiptEvent
  | SSEReactionEvent
  | SSEMessageEditedEvent
  | SSEMessageDeletedEvent;

export interface ConversationHandlers {
  onMessage?: (message: SSEMessageEvent['message'], isMine: boolean) => void;
  onTyping?: (userId: string, userName: string, isTyping: boolean) => void;
  onReadReceipt?: (messageIds: string[], readerId: string) => void;
  onReaction?: (messageId: string, emoji: string, action: 'added' | 'removed', userId: string) => void;
  onMessageEdited?: (messageId: string, newContent: string, editorId: string) => void;
  onMessageDeleted?: (messageId: string, deletedBy: string) => void;
}
