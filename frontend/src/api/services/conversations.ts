/**
 * Conversations Service Layer
 *
 * Provides API functions and React Query hooks for the per-user-pair conversation system.
 * This service communicates with /api/v1/conversations endpoints.
 *
 * Phase 4: Conversation List Migration
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { withApiBase } from '@/lib/apiBase';
import type {
  ConversationListResponse,
  ConversationDetail,
  ConversationMessagesResponse,
  CreateConversationResponse,
  SendMessageResponse,
  ConversationStateFilter,
  ListConversationsParams,
  GetMessagesParams,
} from '@/types/conversation';

// Query keys for React Query cache management
export const conversationQueryKeys = {
  all: ['conversations'] as const,
  lists: () => [...conversationQueryKeys.all, 'list'] as const,
  list: (params: ListConversationsParams) => [...conversationQueryKeys.lists(), params] as const,
  details: () => [...conversationQueryKeys.all, 'detail'] as const,
  detail: (id: string) => [...conversationQueryKeys.details(), id] as const,
  messages: (conversationId: string) => [...conversationQueryKeys.all, 'messages', conversationId] as const,
  messagesWithParams: (conversationId: string, params: GetMessagesParams) =>
    [...conversationQueryKeys.messages(conversationId), params] as const,
};

// Stale times for different query types
const STALE_TIMES = {
  list: 30 * 1000, // 30 seconds
  detail: 60 * 1000, // 1 minute
  messages: 60 * 1000, // 1 minute
};

// =============================================================================
// API Functions (Imperative)
// =============================================================================

/**
 * List all conversations for the current user.
 * Returns one entry per conversation partner.
 */
export async function listConversations(
  params: ListConversationsParams = {}
): Promise<ConversationListResponse> {
  const searchParams = new URLSearchParams();

  if (params.state) {
    searchParams.set('state', params.state);
  }
  if (params.limit) {
    searchParams.set('limit', params.limit.toString());
  }
  if (params.cursor) {
    searchParams.set('cursor', params.cursor);
  }

  const queryString = searchParams.toString();
  const url = queryString
    ? `/api/v1/conversations?${queryString}`
    : '/api/v1/conversations';

  const response = await fetch(withApiBase(url), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to list conversations: ${response.status}`);
  }

  return response.json();
}

/**
 * Get details for a single conversation.
 */
export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  const response = await fetch(withApiBase(`/api/v1/conversations/${conversationId}`), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to get conversation: ${response.status}`);
  }

  return response.json();
}

/**
 * Create or get existing conversation with an instructor.
 * Used for pre-booking messaging.
 */
export async function createConversation(
  instructorId: string,
  initialMessage?: string
): Promise<CreateConversationResponse> {
  const response = await fetch(withApiBase('/api/v1/conversations'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      instructor_id: instructorId,
      initial_message: initialMessage,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to create conversation: ${response.status}`);
  }

  return response.json();
}

/**
 * Get messages for a conversation with pagination.
 */
export async function getMessages(
  conversationId: string,
  params: GetMessagesParams = {}
): Promise<ConversationMessagesResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit) {
    searchParams.set('limit', params.limit.toString());
  }
  if (params.before) {
    searchParams.set('before', params.before);
  }
  if (params.booking_id) {
    searchParams.set('booking_id', params.booking_id);
  }

  const queryString = searchParams.toString();
  const url = queryString
    ? `/api/v1/conversations/${conversationId}/messages?${queryString}`
    : `/api/v1/conversations/${conversationId}/messages`;

  const response = await fetch(withApiBase(url), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to get messages: ${response.status}`);
  }

  return response.json();
}

/**
 * Send a message in a conversation.
 */
export async function sendMessage(
  conversationId: string,
  content: string,
  bookingId?: string
): Promise<SendMessageResponse> {
  const response = await fetch(withApiBase(`/api/v1/conversations/${conversationId}/messages`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      content,
      booking_id: bookingId,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to send message: ${response.status}`);
  }

  return response.json();
}

/**
 * Send typing indicator for a conversation.
 */
export async function sendTypingIndicator(
  conversationId: string,
  isTyping: boolean = true
): Promise<void> {
  await fetch(withApiBase(`/api/v1/conversations/${conversationId}/typing`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ is_typing: isTyping }),
  });
}

/**
 * Update conversation state (archive/trash/restore).
 * Note: This endpoint is at /api/v1/conversations/{id}/state
 */
export async function updateConversationState(
  conversationId: string,
  state: ConversationStateFilter
): Promise<void> {
  const response = await fetch(withApiBase(`/api/v1/conversations/${conversationId}/state`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ state }),
  });

  if (!response.ok) {
    throw new Error(`Failed to update conversation state: ${response.status}`);
  }
}

// =============================================================================
// React Query Hooks
// =============================================================================

/**
 * Hook for listing conversations with React Query.
 */
export function useConversationList(params: ListConversationsParams = {}, enabled = true) {
  return useQuery({
    queryKey: conversationQueryKeys.list(params),
    queryFn: () => listConversations(params),
    staleTime: STALE_TIMES.list,
    enabled,
  });
}

/**
 * Hook for getting a single conversation's details.
 */
export function useConversationDetail(conversationId: string, enabled = true) {
  return useQuery({
    queryKey: conversationQueryKeys.detail(conversationId),
    queryFn: () => getConversation(conversationId),
    staleTime: STALE_TIMES.detail,
    enabled: enabled && !!conversationId,
  });
}

/**
 * Hook for getting messages in a conversation.
 */
export function useConversationMessages(
  conversationId: string,
  params: GetMessagesParams = {},
  enabled = true
) {
  return useQuery({
    queryKey: conversationQueryKeys.messagesWithParams(conversationId, params),
    queryFn: () => getMessages(conversationId, params),
    staleTime: STALE_TIMES.messages,
    enabled: enabled && !!conversationId,
  });
}

/**
 * Hook for creating a conversation.
 */
export function useCreateConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      instructorId,
      initialMessage,
    }: {
      instructorId: string;
      initialMessage?: string;
    }) => createConversation(instructorId, initialMessage),
    onSuccess: () => {
      // Invalidate conversation list to include the new conversation
      void queryClient.invalidateQueries({ queryKey: conversationQueryKeys.lists() });
    },
  });
}

/**
 * Hook for sending a message.
 */
export function useSendConversationMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      conversationId,
      content,
      bookingId,
    }: {
      conversationId: string;
      content: string;
      bookingId?: string;
    }) => sendMessage(conversationId, content, bookingId),
    onSuccess: (_data, variables) => {
      // Invalidate messages for the conversation
      void queryClient.invalidateQueries({
        queryKey: conversationQueryKeys.messages(variables.conversationId),
      });
      // Also invalidate list to update last_message preview
      void queryClient.invalidateQueries({ queryKey: conversationQueryKeys.lists() });
    },
  });
}

/**
 * Hook for sending typing indicator for a conversation.
 */
export function useSendConversationTyping() {
  return useMutation({
    mutationFn: ({
      conversationId,
      isTyping,
    }: {
      conversationId: string;
      isTyping?: boolean;
    }) => sendTypingIndicator(conversationId, isTyping ?? true),
  });
}

/**
 * Hook for updating conversation state.
 */
export function useUpdateConversationState() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      conversationId,
      state,
    }: {
      conversationId: string;
      state: ConversationStateFilter;
    }) => updateConversationState(conversationId, state),
    onSuccess: () => {
      // Invalidate all conversation queries to refresh lists
      void queryClient.invalidateQueries({ queryKey: conversationQueryKeys.all });
    },
  });
}

/**
 * Convenience export for all imperative API functions.
 */
export const conversationService = {
  list: listConversations,
  getById: getConversation,
  create: createConversation,
  getMessages,
  sendMessage,
  updateState: updateConversationState,
};
