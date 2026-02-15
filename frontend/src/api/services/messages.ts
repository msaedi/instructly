/**
 * Messages Service Layer
 *
 * Domain-friendly wrappers around messaging endpoints.
 * Components should use these hooks instead of calling fetch directly.
 */

import { useEffect, useRef } from 'react';
import type { UseQueryOptions } from '@tanstack/react-query';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/src/api/queryKeys';
import { withApiBase, withApiBaseForRequest } from '@/lib/apiBase';
import type { components } from '@/features/shared/api/types';

type MessageConfig = components['schemas']['MessageConfigResponse'];
type UnreadCount = components['schemas']['UnreadCountResponse'];
type ConversationMessages = components['schemas']['MessagesResponse'];
type MarkReadPayload = components['schemas']['MarkMessagesReadRequest'];
type MarkReadResult = components['schemas']['MarkMessagesReadResponse'];
type DeleteMessageResult = components['schemas']['DeleteMessageResponse'];
type EditMessagePayload = components['schemas']['EditMessageRequest'];
type ReactionPayload = components['schemas']['ReactionRequest'];

/**
 * Get message configuration (edit window, etc.).
 *
 * This is public data - no auth required.
 *
 * @example
 * ```tsx
 * function MessageSettings() {
 *   const { data: config } = useMessageConfig();
 *
 *   return <div>Edit window: {config?.edit_window_minutes} minutes</div>;
 * }
 * ```
 */
export function useMessageConfig() {
  return useQuery({
    queryKey: queryKeys.messages.config,
    queryFn: async () => {
      const res = await fetch(withApiBase('/api/v1/messages/config'), {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      });
      if (!res.ok) {
        throw new Error('Failed to load message config');
      }
      return res.json() as Promise<MessageConfig>;
    },
    staleTime: 1000 * 60 * 60,
  });
}

/**
 * Get unread message count for current user.
 *
 * @param enabled - Whether the query should be enabled (default: true)
 * @example
 * ```tsx
 * function MessageBadge() {
 *   const { data } = useUnreadCount();
 *
 *   if (!data?.unread_count) return null;
 *
 *   return <span className="badge">{data.unread_count}</span>;
 * }
 * ```
 */
export function useUnreadCount(enabled: boolean = true) {
  return useQuery({
    queryKey: queryKeys.messages.unreadCount,
    queryFn: async () => {
      const res = await fetch(withApiBase('/api/v1/messages/unread-count'), {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      });
      if (!res.ok) {
        throw new Error('Failed to load unread count');
      }
      return res.json() as Promise<UnreadCount>;
    },
    staleTime: 1000 * 30,
    enabled,
    refetchInterval: 1000 * 30,
  });
}

/**
 * Get message history for a conversation (Phase 7).
 *
 * Fetches ALL messages in a conversation across all bookings between the same
 * student-instructor pair.
 *
 * @param conversationId - ULID of the conversation
 * @param limit - Number of messages per page (default: 50)
 * @param before - Cursor for pagination (message ID)
 * @param enabled - Whether the query should be enabled
 * @example
 * ```tsx
 * function ChatMessages({ conversationId }: { conversationId: string }) {
 *   const { data, isLoading } = useConversationMessages(conversationId);
 *
 *   if (isLoading) return <div>Loading messages...</div>;
 *
 *   return (
 *     <div>
 *       {data?.messages.map(msg => (
 *         <div key={msg.id}>{msg.content}</div>
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useConversationMessages(
  conversationId: string | undefined,
  limit: number = 50,
  before?: string,
  enabled: boolean = true,
  options?: Omit<
    UseQueryOptions<ConversationMessages, Error, ConversationMessages>,
    'queryKey' | 'queryFn' | 'onSuccess' | 'onError'
  > & {
    onSuccess?: (data: ConversationMessages) => void;
    onError?: (error: Error) => void;
  }
) {
  const pagination = before ? { limit, before } : { limit };
  const { onSuccess, onError, ...queryOptions } = options ?? {};
  const lastSuccessAtRef = useRef(0);
  const lastErrorAtRef = useRef(0);

  const query = useQuery<ConversationMessages, Error>({
    queryKey: queryKeys.messages.conversationMessages(conversationId ?? '', pagination),
    queryFn: async (): Promise<ConversationMessages> => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (before) params.append('before', before);
      const response = await fetch(
        withApiBase(`/api/v1/conversations/${conversationId}/messages?${params}`),
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
        }
      );
      if (!response.ok) {
        throw new Error('Failed to fetch conversation messages');
      }
      return (await response.json()) as ConversationMessages;
    },
    staleTime: 1000 * 60, // 1 minute
    enabled: enabled && !!conversationId,
    ...queryOptions,
  });

  useEffect(() => {
    if (!onSuccess || !query.isSuccess || !query.data) {
      return;
    }
    if (query.dataUpdatedAt === lastSuccessAtRef.current) {
      return;
    }
    lastSuccessAtRef.current = query.dataUpdatedAt;
    onSuccess(query.data);
  }, [onSuccess, query.data, query.dataUpdatedAt, query.isSuccess]);

  useEffect(() => {
    if (!onError || !query.isError || !query.error) {
      return;
    }
    if (query.errorUpdatedAt === lastErrorAtRef.current) {
      return;
    }
    lastErrorAtRef.current = query.errorUpdatedAt;
    onError(query.error);
  }, [onError, query.error, query.errorUpdatedAt, query.isError]);

  return query;
}

/**
 * Mark messages as read mutation.
 *
 * Can mark either all messages in a booking OR specific message IDs.
 * Automatically invalidates the unread count query on success.
 *
 * @example
 * ```tsx
 * function ChatView({ bookingId }: { bookingId: string }) {
 *   const markRead = useMarkMessagesAsRead();
 *
 *   useEffect(() => {
 *     // Mark all messages in booking as read when viewing
 *     markRead.mutate({ data: { booking_id: bookingId } });
 *   }, [bookingId]);
 * }
 * ```
 */
export function useMarkMessagesAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: MarkReadPayload): Promise<MarkReadResult> => {
      const response = await fetch(withApiBaseForRequest('/api/v1/messages/mark-read', 'POST'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(
          message || `Failed to mark messages as read (status ${response.status})`
        );
      }

      return response.json() as Promise<MarkReadResult>;
    },
    onSuccess: () => {
      // Invalidate unread count so dashboard badge updates
      void queryClient.invalidateQueries({
        queryKey: queryKeys.messages.unreadCount,
      });
    },
  });
}

/**
 * Delete message mutation.
 *
 * Soft deletes a message - only the sender can delete their own messages.
 *
 * @example
 * ```tsx
 * function MessageItem({ messageId }: { messageId: string }) {
 *   const deleteMessage = useDeleteMessage();
 *
 *   const handleDelete = async () => {
 *     await deleteMessage.mutateAsync({ messageId });
 *   };
 *
 *   return <button onClick={handleDelete}>Delete</button>;
 * }
 * ```
 */
export function useDeleteMessage() {
  return useMutation({
    mutationFn: async ({ messageId }: { messageId: string }): Promise<DeleteMessageResult> => {
      const res = await fetch(withApiBaseForRequest(`/api/v1/messages/${messageId}`, 'DELETE'), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      });
      if (!res.ok) {
        const message = await res.text();
        throw new Error(message || 'Failed to delete message');
      }
      return res.json() as Promise<DeleteMessageResult>;
    },
  });
}

/**
 * Edit message mutation.
 *
 * Only the sender can edit their own messages within the edit window.
 *
 * @example
 * ```tsx
 * function EditMessageForm({ messageId, content }: Props) {
 *   const editMessage = useEditMessage();
 *   const [text, setText] = useState(content);
 *
 *   const handleSave = async () => {
 *     await editMessage.mutateAsync({
 *       messageId,
 *       data: { content: text }
 *     });
 *   };
 *
 *   return <input value={text} onChange={e => setText(e.target.value)} />;
 * }
 * ```
 */
export function useEditMessage() {
  return useMutation({
    mutationFn: async ({
      messageId,
      data,
    }: {
      messageId: string;
      data: EditMessagePayload;
    }): Promise<void> => {
      const res = await fetch(withApiBaseForRequest(`/api/v1/messages/${messageId}`, 'PATCH'), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const message = await res.text();
        throw new Error(message || 'Failed to edit message');
      }
    },
  });
}

/**
 * Add reaction mutation.
 *
 * Adds an emoji reaction to a message.
 *
 * @example
 * ```tsx
 * function ReactionButton({ messageId }: { messageId: string }) {
 *   const addReaction = useAddReaction();
 *
 *   const handleReact = async (emoji: string) => {
 *     await addReaction.mutateAsync({
 *       messageId,
 *       data: { emoji }
 *     });
 *   };
 *
 *   return <button onClick={() => handleReact('👍')}>Like</button>;
 * }
 * ```
 */
export function useAddReaction() {
  return useMutation({
    mutationFn: async ({
      messageId,
      data,
    }: {
      messageId: string;
      data: ReactionPayload;
    }): Promise<void> => {
      const res = await fetch(withApiBaseForRequest(`/api/v1/messages/${messageId}/reactions`, 'POST'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const message = await res.text();
        throw new Error(message || 'Failed to add reaction');
      }
    },
  });
}

/**
 * Remove reaction mutation.
 *
 * Removes an emoji reaction from a message.
 *
 * @example
 * ```tsx
 * function ReactionBadge({ messageId, emoji }: Props) {
 *   const removeReaction = useRemoveReaction();
 *
 *   const handleRemove = async () => {
 *     await removeReaction.mutateAsync({
 *       messageId,
 *       data: { emoji }
 *     });
 *   };
 *
 *   return <button onClick={handleRemove}>{emoji} ✕</button>;
 * }
 * ```
 */
export function useRemoveReaction() {
  return useMutation({
    mutationFn: async ({
      messageId,
      data,
    }: {
      messageId: string;
      data: ReactionPayload;
    }): Promise<void> => {
      const res = await fetch(withApiBaseForRequest(`/api/v1/messages/${messageId}/reactions`, 'DELETE'), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const message = await res.text();
        throw new Error(message || 'Failed to remove reaction');
      }
    },
  });
}

/**
 * Imperative API functions for use in useEffect or other non-hook contexts.
 *
 * Use these when you need to call the API directly without React Query hooks.
 */

/**
 * Fetch message config imperatively.
 *
 * @example
 * ```tsx
 * const config = await fetchMessageConfig();
 * setEditWindow(config.edit_window_minutes);
 * ```
 */
export async function fetchMessageConfig() {
  const response = await fetch(withApiBase('/api/v1/messages/config'), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch message config (status ${response.status})`);
  }

  return response.json() as Promise<MessageConfig>;
}

/**
 * Fetch unread count imperatively.
 *
 * @example
 * ```tsx
 * const { unread_count } = await fetchUnreadCount();
 * ```
 */
export async function fetchUnreadCount() {
  const response = await fetch(withApiBase('/api/v1/messages/unread-count'), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch unread count (status ${response.status})`);
  }

  return response.json() as Promise<UnreadCount>;
}

/**
 * Mark messages as read imperatively.
 *
 * @example
 * ```tsx
 * await markMessagesAsReadImperative({ conversation_id: '01ABC...' });
 * ```
 */
export async function markMessagesAsReadImperative(body: MarkReadPayload) {
  const response = await fetch(withApiBaseForRequest('/api/v1/messages/mark-read', 'POST'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to mark messages as read (status ${response.status})`);
  }

  return response.json() as Promise<MarkReadResult>;
}

/**
 * Delete a message imperatively.
 *
 * @example
 * ```tsx
 * await deleteMessageImperative('01XYZ...');
 * ```
 */
export async function deleteMessageImperative(messageId: string) {
  const response = await fetch(withApiBaseForRequest(`/api/v1/messages/${messageId}`, 'DELETE'), {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to delete message (status ${response.status})`);
  }

  return response.json() as Promise<DeleteMessageResult>;
}

/**
 * Type exports for convenience
 */
export type { EditMessagePayload, ReactionPayload };
