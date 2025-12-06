// frontend/types/conversation.ts
/**
 * Types for the per-user-pair conversation system.
 *
 * Phase 4: One conversation per student-instructor pair, regardless of bookings.
 * These types match the backend schemas in app/schemas/conversation.py
 */

/**
 * Minimal user info for conversation list and detail views.
 */
export interface UserSummary {
  id: string;
  first_name: string;
  last_initial: string;
  profile_photo_url?: string | null;
}

/**
 * Minimal booking info shown in conversation context.
 */
export interface BookingSummary {
  id: string;
  date: string; // YYYY-MM-DD
  start_time: string; // HH:MM
  service_name: string;
}

/**
 * Preview of the last message in a conversation.
 */
export interface LastMessage {
  content: string;
  created_at: string; // ISO datetime
  is_from_me: boolean;
}

/**
 * Reaction on a message.
 */
export interface ReactionInfo {
  user_id: string;
  emoji: string;
}

/**
 * Read receipt entry for messages.
 */
export interface ReadReceiptEntry {
  user_id: string;
  read_at: string;
}

/**
 * Single conversation in the inbox list.
 */
export interface ConversationListItem {
  id: string;
  other_user: UserSummary;
  last_message?: LastMessage | null;
  unread_count: number;
  next_booking?: BookingSummary | null;
  upcoming_bookings: BookingSummary[];
  upcoming_booking_count: number;
  state: ConversationStateFilter;
}

/**
 * Response for GET /api/v1/conversations
 */
export interface ConversationListResponse {
  conversations: ConversationListItem[];
  next_cursor?: string | null;
}

/**
 * Full conversation details.
 */
export interface ConversationDetail {
  id: string;
  other_user: UserSummary;
  next_booking?: BookingSummary | null;
  upcoming_bookings: BookingSummary[];
  state: ConversationStateFilter;
  created_at: string;
}

/**
 * Single message in a conversation.
 */
export interface ConversationMessage {
  id: string;
  content: string;
  sender_id: string | null; // null for system messages
  is_from_me: boolean;
  message_type: string; // 'user' | 'system_booking_created' | 'system_booking_cancelled' | etc
  booking_id?: string | null;
  booking_details?: BookingSummary | null;
  created_at: string;
  delivered_at?: string | null;
  read_by: ReadReceiptEntry[];
  reactions: ReactionInfo[];
}

/**
 * Response for GET /api/v1/conversations/{id}/messages
 */
export interface ConversationMessagesResponse {
  messages: ConversationMessage[];
  has_more: boolean;
  next_cursor?: string | null;
}

/**
 * Request to create a pre-booking conversation.
 */
export interface CreateConversationRequest {
  instructor_id: string;
  initial_message?: string;
}

/**
 * Response for POST /api/v1/conversations
 */
export interface CreateConversationResponse {
  id: string;
  created: boolean; // false if conversation already existed
}

/**
 * Request to send a message in a conversation.
 */
export interface SendMessageRequest {
  content: string;
  booking_id?: string; // Optional explicit booking context
}

/**
 * Response for POST /api/v1/conversations/{id}/messages
 */
export interface SendMessageResponse {
  id: string;
  created_at: string;
}

/**
 * Conversation state filter options.
 */
export type ConversationStateFilter = 'active' | 'archived' | 'trashed';

/**
 * Parameters for listing conversations.
 */
export interface ListConversationsParams {
  state?: ConversationStateFilter;
  limit?: number;
  cursor?: string;
}

/**
 * Parameters for getting messages.
 */
export interface GetMessagesParams {
  limit?: number;
  before?: string; // Cursor for pagination
  booking_id?: string; // Filter by booking
}
