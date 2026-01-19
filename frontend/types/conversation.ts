// frontend/types/conversation.ts
/**
 * Types for the per-user-pair conversation system.
 *
 * Re-exported from the generated OpenAPI schema via the shim layer.
 */

import type { components } from '@/features/shared/api/types';

export type UserSummary = components['schemas']['UserSummary'];
export type BookingSummary = components['schemas']['BookingSummary'];
export type LastMessage = components['schemas']['LastMessage'];
export type ReactionInfo = components['schemas']['ReactionInfo'];
export type ReadReceiptEntry = components['schemas']['ReadReceiptEntry'];
export type ConversationListItem = components['schemas']['ConversationListItem'];
export type ConversationListResponse = components['schemas']['ConversationListResponse'];
export type ConversationDetail = components['schemas']['ConversationDetail'];
export type ConversationMessage = components['schemas']['MessageResponse'];
export type ConversationMessagesResponse = components['schemas']['MessagesResponse'];
export type CreateConversationRequest = components['schemas']['CreateConversationRequest'];
export type CreateConversationResponse = components['schemas']['CreateConversationResponse'];
export type SendMessageRequest = components['schemas']['SendMessageRequest'];
export type SendMessageResponse = components['schemas']['SendMessageResponse'];
export type ConversationStateFilter = components['schemas']['UpdateConversationStateRequest']['state'];

export interface ListConversationsParams {
  state?: ConversationStateFilter;
  limit?: number;
  cursor?: string;
}

export interface GetMessagesParams {
  limit?: number;
  before?: string;
  booking_id?: string;
}
