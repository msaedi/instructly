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

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/src/api/queryKeys';
import { withApiBase } from '@/lib/apiBase';
import {
  useGetMessageConfigApiV1MessagesConfigGet,
  useGetUnreadCountApiV1MessagesUnreadCountGet,
  useGetMessageHistoryApiV1MessagesHistoryBookingIdGet,
  useSendMessageApiV1MessagesSendPost,
  useMarkMessagesAsReadApiV1MessagesMarkReadPost,
  useDeleteMessageApiV1MessagesMessageIdDelete,
  useEditMessageApiV1MessagesMessageIdPatch,
  useAddReactionApiV1MessagesMessageIdReactionsPost,
  useRemoveReactionApiV1MessagesMessageIdReactionsDelete,
  useSendTypingIndicatorApiV1MessagesTypingBookingIdPost,
} from '@/src/api/generated/messages-v1/messages-v1';
import type {
  SendMessageRequest,
  MarkMessagesReadRequest,
  EditMessageRequest,
  ReactionRequest,
  GetMessageHistoryApiV1MessagesHistoryBookingIdGetParams,
} from '@/src/api/generated/instructly.schemas';

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
 * Get message history for a booking.
 *
 * @param bookingId - ULID of the booking
 * @param limit - Number of messages per page (default: 50)
 * @param offset - Pagination offset (default: 0)
 * @param enabled - Whether the query should be enabled
 * @example
 * ```tsx
 * function ChatMessages({ bookingId }: { bookingId: string }) {
 *   const { data, isLoading } = useMessageHistory(bookingId);
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
export function useMessageHistory(
  bookingId: string,
  limit: number = 50,
  offset: number = 0,
  enabled: boolean = true
) {
  const params: GetMessageHistoryApiV1MessagesHistoryBookingIdGetParams = {
    limit,
    offset,
  };

  return useGetMessageHistoryApiV1MessagesHistoryBookingIdGet(bookingId, params, {
    query: {
      queryKey: queryKeys.messages.history(bookingId, { limit, offset }),
      staleTime: 1000 * 60, // 1 minute
      enabled: enabled && !!bookingId,
    },
  });
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
    message_type: string;
    booking_id: string | null;
    created_at: string;
    delivered_at: string | null;
    read_by: string[];
  }>;
  has_more: boolean;
  next_cursor: string | null;
}

/**
 * Response type for conversation messages endpoint.
 * Phase 7: Fetches ALL messages in a conversation (across all bookings).
 * Messages are transformed to match MessageResponse structure for compatibility.
 */
interface ConversationMessagesResponse {
  messages: Array<{
    id: string;
    content: string;
    sender_id: string;
    booking_id: string;
    created_at: string;
    updated_at: string;
    delivered_at?: string | null;
    read_by?: string[];
    is_deleted?: boolean;
    edited_at?: string;
  }>;
  has_more: boolean;
  next_cursor: string | null;
}

/**
 * Get message history for a conversation (Phase 7).
 *
 * Unlike useMessageHistory which fetches by booking_id, this hook fetches
 * ALL messages in a conversation across all bookings between the same
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
          sender_id: msg.sender_id ?? '', // Fallback for system messages
          booking_id: msg.booking_id ?? '', // Fallback if null
          created_at: msg.created_at,
          updated_at: msg.created_at, // Use created_at as fallback for updated_at
          delivered_at: msg.delivered_at,
          read_by: msg.read_by,
          is_deleted: false, // Default value
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
 * Send message mutation.
 *
 * @example
 * ```tsx
 * function ChatInput({ bookingId }: { bookingId: string }) {
 *   const sendMessage = useSendMessage();
 *   const [text, setText] = useState('');
 *
 *   const handleSend = async () => {
 *     await sendMessage.mutateAsync({
 *       data: { booking_id: bookingId, content: text }
 *     });
 *     setText('');
 *   };
 *
 *   return <input value={text} onChange={e => setText(e.target.value)} />;
 * }
 * ```
 */
export function useSendMessage() {
  return useSendMessageApiV1MessagesSendPost();
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
  return useMarkMessagesAsReadApiV1MessagesMarkReadPost({
    mutation: {
      onSuccess: () => {
        // Invalidate unread count so dashboard badge updates
        void queryClient.invalidateQueries({
          queryKey: queryKeys.messages.unreadCount,
        });
      },
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
 * Send typing indicator mutation.
 *
 * Sends a typing indicator to other participants (ephemeral, no DB writes).
 * Rate limited to 1 per second.
 *
 * @example
 * ```tsx
 * function ChatInput({ bookingId }: { bookingId: string }) {
 *   const sendTyping = useSendTypingIndicator();
 *
 *   const handleTyping = useDebouncedCallback(() => {
 *     sendTyping.mutate({ bookingId });
 *   }, 1000);
 *
 *   return <input onChange={handleTyping} />;
 * }
 * ```
 */
export function useSendTypingIndicator() {
  return useSendTypingIndicatorApiV1MessagesTypingBookingIdPost();
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
 * Fetch message history imperatively.
 *
 * @example
 * ```tsx
 * const { messages, has_more } = await fetchMessageHistory('01ABC...', { limit: 50 });
 * ```
 */
export { getMessageHistoryApiV1MessagesHistoryBookingIdGet as fetchMessageHistory } from '@/src/api/generated/messages-v1/messages-v1';

/**
 * Send a message imperatively.
 *
 * @example
 * ```tsx
 * const response = await sendMessageImperative({
 *   booking_id: '01ABC...',
 *   content: 'Hello!'
 * });
 * ```
 */
export { sendMessageApiV1MessagesSendPost as sendMessageImperative } from '@/src/api/generated/messages-v1/messages-v1';

/**
 * Mark messages as read imperatively.
 *
 * @example
 * ```tsx
 * await markMessagesAsReadImperative({ booking_id: '01ABC...' });
 * ```
 */
export { markMessagesAsReadApiV1MessagesMarkReadPost as markMessagesAsReadImperative } from '@/src/api/generated/messages-v1/messages-v1';

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
export type {
  SendMessageRequest,
  MarkMessagesReadRequest,
  EditMessageRequest,
  ReactionRequest,
  GetMessageHistoryApiV1MessagesHistoryBookingIdGetParams as MessageHistoryParams,
};
