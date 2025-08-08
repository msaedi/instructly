// frontend/hooks/useMessageQueries.ts
/**
 * React Query hooks for message-related data fetching.
 *
 * These hooks handle:
 * - Message history with pagination
 * - Unread message counts
 * - Marking messages as read
 * - Message deletion
 *
 * All hooks follow React Query best practices with:
 * - Proper cache invalidation
 * - Optimistic updates where appropriate
 * - Stale time configuration for optimal performance
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  messageService,
  MessagesHistoryResponse,
  UnreadCountResponse,
  SendMessageRequest,
  MarkMessagesReadRequest
} from '@/services/messageService';
import { logger } from '@/lib/logger';

// Query key factory for consistent cache keys
export const messageQueryKeys = {
  all: ['messages'] as const,
  history: (bookingId: number) => ['messages', 'history', bookingId] as const,
  historyPaginated: (bookingId: number, limit: number, offset: number) =>
    ['messages', 'history', bookingId, { limit, offset }] as const,
  unreadCount: () => ['messages', 'unread-count'] as const,
};

/**
 * Hook for fetching message history with pagination
 */
export function useMessageHistory(
  bookingId: number,
  limit: number = 50,
  offset: number = 0,
  enabled: boolean = true
) {
  return useQuery<MessagesHistoryResponse, Error>({
    queryKey: messageQueryKeys.historyPaginated(bookingId, limit, offset),
    queryFn: () => messageService.getMessageHistory(bookingId, limit, offset),
    enabled: enabled && bookingId > 0,
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 10, // 10 minutes (formerly cacheTime)
    refetchOnWindowFocus: true,
    refetchOnMount: true,
    retry: 2,
  });
}

/**
 * Hook for fetching unread message count
 */
export function useUnreadCount(enabled: boolean = true) {
  return useQuery<UnreadCountResponse, Error>({
    queryKey: messageQueryKeys.unreadCount(),
    queryFn: () => messageService.getUnreadCount(),
    enabled,
    staleTime: 1000 * 60, // 1 minute
    gcTime: 1000 * 60 * 5, // 5 minutes
    refetchOnWindowFocus: true,
    refetchInterval: 1000 * 60, // Refetch every minute
    retry: 1,
  });
}

/**
 * Hook for sending a message
 */
export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: SendMessageRequest) =>
      messageService.sendMessage(request),
    onSuccess: (data, variables) => {
      // Invalidate message history for this booking
      queryClient.invalidateQueries({
        queryKey: messageQueryKeys.history(variables.booking_id),
      });

      // Invalidate unread count (in case user sees their own message)
      queryClient.invalidateQueries({
        queryKey: messageQueryKeys.unreadCount(),
      });

      logger.info('Message sent and cache invalidated', {
        booking_id: variables.booking_id
      });
    },
    onError: (error, variables) => {
      logger.error('Failed to send message', error, {
        booking_id: variables.booking_id
      });
    },
  });
}

/**
 * Hook for marking messages as read
 */
export function useMarkAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: MarkMessagesReadRequest) =>
      messageService.markMessagesAsRead(request),
    onMutate: async (request) => {
      // Optimistically update unread count
      await queryClient.cancelQueries({
        queryKey: messageQueryKeys.unreadCount(),
      });

      const previousCount = queryClient.getQueryData<UnreadCountResponse>(
        messageQueryKeys.unreadCount()
      );

      if (previousCount) {
        // Optimistically reduce count (we don't know exact amount, so just set to 0 for this booking)
        queryClient.setQueryData<UnreadCountResponse>(
          messageQueryKeys.unreadCount(),
          (old) => {
            if (!old) return old;
            // This is approximate - real count will come from server
            return {
              ...old,
              unread_count: Math.max(0, old.unread_count - 1),
            };
          }
        );
      }

      return { previousCount };
    },
    onSuccess: (data, variables) => {
      // Invalidate unread count to get accurate number
      queryClient.invalidateQueries({
        queryKey: messageQueryKeys.unreadCount(),
      });

      // If marking all messages in a booking as read, invalidate that history
      if (variables.booking_id) {
        queryClient.invalidateQueries({
          queryKey: messageQueryKeys.history(variables.booking_id),
        });
      }

      logger.info('Messages marked as read', {
        count: data,
        booking_id: variables.booking_id,
        message_ids: variables.message_ids,
      });
    },
    onError: (error, variables, context) => {
      // Rollback optimistic update on error
      if (context?.previousCount) {
        queryClient.setQueryData(
          messageQueryKeys.unreadCount(),
          context.previousCount
        );
      }

      logger.error('Failed to mark messages as read', error);
    },
  });
}

/**
 * Hook for deleting a message
 */
export function useDeleteMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (messageId: number) =>
      messageService.deleteMessage(messageId),
    onSuccess: (_, messageId) => {
      // Invalidate all message history queries
      queryClient.invalidateQueries({
        queryKey: messageQueryKeys.all,
      });

      logger.info('Message deleted', { message_id: messageId });
    },
    onError: (error, messageId) => {
      logger.error('Failed to delete message', error, {
        message_id: messageId
      });
    },
  });
}

/**
 * Hook to prefetch message history
 * Useful for preloading chat data before user opens it
 */
export function usePrefetchMessageHistory() {
  const queryClient = useQueryClient();

  return (bookingId: number, limit: number = 50, offset: number = 0) => {
    return queryClient.prefetchQuery({
      queryKey: messageQueryKeys.historyPaginated(bookingId, limit, offset),
      queryFn: () => messageService.getMessageHistory(bookingId, limit, offset),
      staleTime: 1000 * 60 * 5, // 5 minutes
    });
  };
}
