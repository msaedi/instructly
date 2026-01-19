/**
 * useConversations - Hook for loading and managing conversations
 *
 * Phase 4: Updated to use the new per-user-pair conversation API.
 * Uses /api/v1/conversations endpoint with React Query for caching.
 * Integrates with SSE to invalidate cache when new messages arrive.
 */

import { useMemo, useEffect, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useMessageStream } from '@/providers/UserMessageStreamProvider';
import { withApiBase } from '@/lib/apiBase';
import type { ConversationEntry } from '../types';
import type { ConversationListItem, ConversationListResponse } from '@/types/conversation';
import type { components } from '@/features/shared/api/types';
import { getInitials, formatRelativeTimestamp } from '../utils';

export type UseConversationsOptions = {
  currentUserId: string | undefined;
  isLoadingUser: boolean;
  stateFilter?: 'archived' | 'trashed' | null | undefined;
  typeFilter?: 'student' | 'platform' | null | undefined;
};

export type UseConversationsResult = {
  conversations: ConversationEntry[];
  setConversations: React.Dispatch<React.SetStateAction<ConversationEntry[]>>;
  isLoading: boolean;
  error: string | null;
  totalUnread: number;
  unreadConversations: ConversationEntry[];
  unreadConversationsCount: number;
  loadConversations: () => void;
  stateCounts?: {
    active: number;
    archived: number;
    trashed: number;
  } | undefined;
};

// Query key factory for conversation queries
const conversationKeys = {
  all: ['conversations'] as const,
  list: (state?: string | null) => [...conversationKeys.all, 'list', state] as const,
};

// Stale time for conversation list queries
const STALE_TIME = 30 * 1000; // 30 seconds
const REFETCH_INTERVAL = 30 * 1000; // 30 seconds

// API fetch function for conversation list
async function fetchConversations(stateFilter?: string | null): Promise<{
  conversations: ConversationListItem[];
  total_unread: number;
  unread_conversations: number;
  state_counts: { active: number; archived: number; trashed: number } | undefined;
}> {
  const params = new URLSearchParams();
  if (stateFilter) {
    params.set('state', stateFilter);
  }
  params.set('limit', '50'); // Reasonable default limit

  const queryString = params.toString();
  const url = queryString
    ? `/api/v1/conversations?${queryString}`
    : '/api/v1/conversations';

  const response = await fetch(withApiBase(url), {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch conversations: ${response.status}`);
  }

  const data = (await response.json()) as ConversationListResponse;

  // Calculate unread counts from the response
  const totalUnread = data.conversations?.reduce(
    (sum: number, conv: ConversationListItem) => sum + conv.unread_count,
    0
  ) ?? 0;
  const unreadConversations = data.conversations?.filter(
    (conv: ConversationListItem) => conv.unread_count > 0
  ).length ?? 0;

  return {
    conversations: data.conversations ?? [],
    total_unread: totalUnread,
    unread_conversations: unreadConversations,
    // TODO: Backend should return state_counts in Phase 3
    state_counts: undefined,
  };
}

export function useConversations({
  currentUserId,
  isLoadingUser,
  stateFilter,
  typeFilter,
}: UseConversationsOptions): UseConversationsResult {
  const queryClient = useQueryClient();
  const { subscribe, isConnected } = useMessageStream();

  // Map state filter for API
  const apiStateFilter = stateFilter === 'archived' ? 'archived'
    : stateFilter === 'trashed' ? 'trashed'
    : 'active';

  // Query key for this specific filter
  const queryKey = conversationKeys.list(apiStateFilter);

  // Fetch conversations using React Query
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey,
    queryFn: () => fetchConversations(apiStateFilter),
    staleTime: STALE_TIME,
    refetchInterval: isConnected ? false : REFETCH_INTERVAL,
    enabled: !isLoadingUser,
  });

  // Invalidate function for SSE callbacks
  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: conversationKeys.all });
  }, [queryClient]);

  // Use ref to store latest invalidate to avoid re-render loop
  const invalidateRef = useRef(invalidate);
  useEffect(() => {
    invalidateRef.current = invalidate;
  }, [invalidate]);

  // Invalidate conversation list when SSE receives a message for ANY conversation
  useEffect(() => {
    const unsubscribe = subscribe('__global__', {
      onMessage: () => {
        // New message arrived - refresh conversation list
        invalidateRef.current();
      },
      onMessageEdited: () => {
        // Edited message may change conversation preview
        invalidateRef.current();
      },
    });

    return unsubscribe;
  }, [subscribe]);

  // Transform backend ConversationListItem to frontend ConversationEntry format
  const conversations = useMemo<ConversationEntry[]>(() => {
    if (!data?.conversations) return [];

    return data.conversations
      .filter((_conv) => {
        // Apply type filter if specified
        if (typeFilter === 'platform') {
          // Platform type not supported in new API yet
          return false;
        }
        return true;
      })
      .map((conv) => {
        // Build display name from other_user
        const displayName = `${conv.other_user.first_name} ${conv.other_user.last_initial}.`;

        // Get initials for avatar
        const avatar = getInitials(
          conv.other_user.first_name,
          conv.other_user.last_initial
        );

        // Format timestamp from last message
        const timestamp = conv.last_message?.created_at
          ? formatRelativeTimestamp(conv.last_message.created_at)
          : '';

        // Get last message content
        const lastMessage = conv.last_message?.content ?? 'No messages yet';

        // The conversation ID is now the actual conversation ID (not booking ID)
        // For backward compatibility, we keep the same structure
        return {
          id: conv.id,
          name: displayName,
          lastMessage: lastMessage.length > 100 ? `${lastMessage.slice(0, 100)}...` : lastMessage,
          timestamp,
          unread: conv.unread_count,
          avatar,
          type: 'student' as const,
          // In the new model, a conversation spans all bookings between users
          // Use upcoming_bookings array from API response
          bookingIds: (conv.upcoming_bookings ?? []).map((b) => b.id),
          primaryBookingId: conv.next_booking?.id ?? null,
          studentId: conv.other_user.id,
          instructorId: currentUserId ?? null,
          latestMessageAt: conv.last_message?.created_at
            ? new Date(conv.last_message.created_at).getTime()
            : 0,
          latestMessageId: null,
          // New fields for the per-user-pair model
          conversationId: conv.id,
          nextBooking: conv.next_booking,
          upcomingBookings: conv.upcoming_bookings ?? [],
          upcomingBookingCount: conv.upcoming_booking_count,
        };
      });
  }, [data, currentUserId, typeFilter]);

  const totalUnread = data?.total_unread ?? 0;
  const unreadConversationsCount = data?.unread_conversations ?? 0;

  const unreadConversations = useMemo(
    () => conversations.filter((convo) => convo.unread > 0),
    [conversations]
  );

  // Dummy setConversations for compatibility with existing code
  const setConversations = useCallback(() => {
    // No-op: conversations are now managed by React Query cache
    // This is here for backward compatibility
  }, []);

  // loadConversations triggers a refresh
  const loadConversations = useCallback(() => {
    void refetch();
  }, [refetch]);

  return {
    conversations,
    setConversations,
    isLoading: isLoadingUser || isLoading,
    error: isError ? 'Unable to load conversations' : null,
    totalUnread,
    unreadConversations,
    unreadConversationsCount,
    loadConversations,
    stateCounts: data?.state_counts,
  };
}

/**
 * useUpdateConversationState - Mutation hook for updating conversation state
 *
 * Allows archiving, trashing, or restoring conversations.
 * Automatically invalidates conversation queries.
 *
 * Phase 4 Note: State updates now use /api/v1/conversations/{conversationId}/state only.
 */
export function useUpdateConversationState() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      conversationId,
      state,
    }: {
      conversationId: string;
      state: 'active' | 'archived' | 'trashed';
    }) => {
      const response = await fetch(
        withApiBase(`/api/v1/conversations/${conversationId}/state`),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ state }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to update conversation state');
      }

      return (await response.json()) as components['schemas']['UpdateConversationStateResponse'];
    },
    onSuccess: () => {
      // Invalidate all conversation-related queries
      void queryClient.invalidateQueries({ queryKey: conversationKeys.all });
    },
  });
}
