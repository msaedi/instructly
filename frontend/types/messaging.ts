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
  | 'reaction_update';

export interface SSEMessageEvent {
  type: 'new_message';
  conversation_id: string;
  is_mine: boolean;
  message: {
    id: string;
    content: string;
    sender_id: string;
    sender_name: string;
    created_at: string;
    booking_id: string;
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

export type SSEEvent =
  | SSEMessageEvent
  | SSETypingEvent
  | SSEReadReceiptEvent
  | SSEReactionEvent;

export interface ConversationHandlers {
  onMessage?: (message: SSEMessageEvent['message'], isMine: boolean) => void;
  onTyping?: (userId: string, userName: string, isTyping: boolean) => void;
  onReadReceipt?: (messageIds: string[], readerId: string) => void;
  onReaction?: (messageId: string, emoji: string, action: 'added' | 'removed', userId: string) => void;
}
