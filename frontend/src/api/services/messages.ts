/**
 * Messages Service Layer
 *
 * Domain-friendly wrappers around Orval-generated messages v1 hooks.
 * This is the ONLY layer that should directly import from generated/messages-v1.
 *
 * Components should use these hooks, not the raw Orval-generated ones.
 *
 * Phase 10: Messages domain migrated to /api/v1/messages
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/src/api/queryKeys';
import { withApiBase } from '@/lib/apiBase';
import {
  useGetMessageConfigApiV1MessagesConfigGet,
  useGetUnreadCountApiV1MessagesUnreadCountGet,
  useDeleteMessageApiV1MessagesMessageIdDelete,
  useEditMessageApiV1MessagesMessageIdPatch,
  useAddReactionApiV1MessagesMessageIdReactionsPost,
  useRemoveReactionApiV1MessagesMessageIdReactionsDelete,
} from '@/src/api/generated/messages-v1/messages-v1';
import type { EditMessageRequest, ReactionRequest } from '@/src/api/generated/instructly.schemas';

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
  return useGetMessageConfigApiV1MessagesConfigGet({
    query: {
      queryKey: queryKeys.messages.config,
      staleTime: 1000 * 60 * 60, // 1 hour - rarely changes
    },
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
  return useGetUnreadCountApiV1MessagesUnreadCountGet({
    query: {
      queryKey: queryKeys.messages.unreadCount,
      staleTime: 1000 * 30, // 30 seconds
      enabled,
      refetchInterval: 1000 * 30, // Poll every 30 seconds - matches conversation refresh
    },
  });
}

/**
 * Reaction info from API response.
 */
interface ReactionInfo {
  user_id: string;
  emoji: string;
}

/**
 * Read receipt entry from API response.
 */
interface ReadReceiptEntry {
  user_id: string;
  read_at: string;
}

/**
 * Raw response type from conversation messages endpoint (before transformation).
 */
interface ConversationMessagesRawResponse {
  messages: Array<{
    id: string;
    content: string;
    sender_id: string | null;
    is_from_me: boolean;
    message_type: string | null;
    booking_id: string | null;
    booking_details?: unknown;
    created_at: string;
    delivered_at: string | null;
    conversation_id?: string | null;
    read_by: ReadReceiptEntry[];
    reactions: ReactionInfo[];
  }>;
  has_more: boolean;
  next_cursor: string | null;
}

/**
 * Response type for conversation messages endpoint.
 * Fetches ALL messages in a conversation (across all bookings).
 * Messages are transformed to match MessageResponse structure for compatibility.
 */
interface ConversationMessagesResponse {
  messages: Array<{
    id: string;
    content: string;
    sender_id: string | null;
    booking_id: string | null;
    conversation_id: string | null;
    created_at: string;
    updated_at: string;
    delivered_at?: string | null;
    read_by?: ReadReceiptEntry[];
    is_deleted?: boolean;
    edited_at?: string;
    reactions?: ReactionInfo[];
    message_type: string;
    is_from_me: boolean;
    booking_details: unknown;
  }>;
  has_more: boolean;
  next_cursor: string | null;
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
  enabled: boolean = true
) {
  const pagination = before ? { limit, before } : { limit };

  return useQuery<ConversationMessagesResponse>({
    queryKey: queryKeys.messages.conversationMessages(conversationId ?? '', pagination),
    queryFn: async (): Promise<ConversationMessagesResponse> => {
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
      const raw = (await response.json()) as ConversationMessagesRawResponse;
      // Transform messages to match MessageResponse structure for Chat.tsx compatibility
      return {
        messages: raw.messages.map((msg) => ({
          id: msg.id,
          content: msg.content,
          sender_id: msg.sender_id ?? null,
          booking_id: msg.booking_id ?? null,
          conversation_id: msg.conversation_id ?? conversationId ?? null,
          created_at: msg.created_at,
          updated_at: msg.created_at,
          delivered_at: msg.delivered_at ?? null,
          read_by: msg.read_by ?? [],
          is_deleted: false,
          reactions: msg.reactions ?? [],
          message_type: msg.message_type ?? 'user',
          is_from_me: msg.is_from_me ?? false,
          booking_details: msg.booking_details ?? null,
        })),
        has_more: raw.has_more,
        next_cursor: raw.next_cursor,
      };
    },
    staleTime: 1000 * 60, // 1 minute
    enabled: enabled && !!conversationId,
  });
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
    mutationFn: async (body: { conversation_id?: string; message_ids?: string[] }) => {
      const response = await fetch(withApiBase('/api/v1/messages/mark-read'), {
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

      return response.json();
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
  return useDeleteMessageApiV1MessagesMessageIdDelete();
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
  return useEditMessageApiV1MessagesMessageIdPatch();
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
  return useAddReactionApiV1MessagesMessageIdReactionsPost();
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
  return useRemoveReactionApiV1MessagesMessageIdReactionsDelete();
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
export { getMessageConfigApiV1MessagesConfigGet as fetchMessageConfig } from '@/src/api/generated/messages-v1/messages-v1';

/**
 * Fetch unread count imperatively.
 *
 * @example
 * ```tsx
 * const { unread_count } = await fetchUnreadCount();
 * ```
 */
export { getUnreadCountApiV1MessagesUnreadCountGet as fetchUnreadCount } from '@/src/api/generated/messages-v1/messages-v1';

/**
 * Mark messages as read imperatively.
 *
 * @example
 * ```tsx
 * await markMessagesAsReadImperative({ conversation_id: '01ABC...' });
 * ```
 */
export async function markMessagesAsReadImperative(body: {
  conversation_id?: string;
  message_ids?: string[];
}) {
  const response = await fetch(withApiBase('/api/v1/messages/mark-read'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Failed to mark messages as read (status ${response.status})`);
  }

  return response.json();
}

/**
 * Delete a message imperatively.
 *
 * @example
 * ```tsx
 * await deleteMessageImperative('01XYZ...');
 * ```
 */
export { deleteMessageApiV1MessagesMessageIdDelete as deleteMessageImperative } from '@/src/api/generated/messages-v1/messages-v1';

/**
 * Type exports for convenience
 */
export type { EditMessageRequest, ReactionRequest };
