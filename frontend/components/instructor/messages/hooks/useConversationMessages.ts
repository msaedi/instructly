/**
 * useConversationMessages - Hook for fetching messages by conversation ID
 *
 * Phase 5: Uses the new /api/v1/conversations/{id}/messages endpoint.
 * Supports pagination via cursor and optional booking filter.
 */

import { useCallback, useMemo } from 'react';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { withApiBase } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import type { ConversationMessage, ConversationMessagesResponse, GetMessagesParams } from '@/types/conversation';
import { conversationQueryKeys } from '@/src/api/services/conversations';

export type UseConversationMessagesOptions = {
  conversationId: string | null | undefined;
  bookingFilter?: string | null;
  limit?: number;
  enabled?: boolean;
};

export type UseConversationMessagesResult = {
  messages: ConversationMessage[];
  isLoading: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  error: string | null;
  fetchNextPage: () => void;
  refetch: () => void;
  invalidate: () => void;
};

// Stale time for message queries
const STALE_TIME = 60 * 1000; // 1 minute

// API fetch function
async function fetchMessages(
  conversationId: string,
  params: GetMessagesParams
): Promise<{
  messages: ConversationMessage[];
  has_more: boolean;
  next_cursor: string | null;
}> {
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

  const response = await fetchWithSessionRefresh(withApiBase(url), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch messages: ${response.status}`);
  }

  const payload = (await response.json()) as ConversationMessagesResponse;
  return {
    ...payload,
    next_cursor: payload.next_cursor ?? null,
  };
}

export function useConversationMessages({
  conversationId,
  bookingFilter,
  limit = 50,
  enabled = true,
}: UseConversationMessagesOptions): UseConversationMessagesResult {
  const queryClient = useQueryClient();

  // Build query key including filter params
  const queryKey = useMemo(() => {
    const params: GetMessagesParams = { limit };
    if (bookingFilter) {
      params.booking_id = bookingFilter;
    }
    return conversationQueryKeys.messagesWithParams(conversationId ?? '', params);
  }, [conversationId, bookingFilter, limit]);

  const {
    data,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    error,
    fetchNextPage: fetchNext,
    refetch,
  } = useInfiniteQuery({
    queryKey,
    queryFn: async ({ pageParam }) => {
      if (!conversationId) {
        throw new Error('No conversation ID provided');
      }
      const params: GetMessagesParams = { limit };
      if (pageParam) {
        params.before = pageParam as string;
      }
      if (bookingFilter) {
        params.booking_id = bookingFilter;
      }
      return fetchMessages(conversationId, params);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    staleTime: STALE_TIME,
    enabled: enabled && !!conversationId,
  });

  // Flatten messages from all pages
  const messages = useMemo(() => {
    if (!data?.pages) return [];
    // Messages come newest-first from API, we want oldest-first for display
    const allMessages = data.pages.flatMap((page) => page.messages);
    return allMessages.reverse();
  }, [data]);

  // Invalidate function for cache refresh
  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: conversationQueryKeys.messages(conversationId ?? ''),
    });
  }, [queryClient, conversationId]);

  const fetchNextPage = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNext();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNext]);

  return {
    messages,
    isLoading,
    isFetchingNextPage,
    hasNextPage: hasNextPage ?? false,
    error: error ? 'Unable to load messages' : null,
    fetchNextPage,
    refetch: () => void refetch(),
    invalidate,
  };
}
