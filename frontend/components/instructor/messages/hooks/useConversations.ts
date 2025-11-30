/**
 * useConversations - Hook for loading and managing conversations
 *
 * Uses the new inbox-state endpoint with ETag caching for efficient polling.
 * Integrates with SSE to invalidate cache when new messages arrive.
 */

import { useMemo, useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useInboxState } from '@/hooks/useInboxState';
import { useMessageStream } from '@/providers/UserMessageStreamProvider';
import { withApiBase } from '@/lib/apiBase';
import type { ConversationEntry } from '../types';
import { getInitials, formatRelativeTime } from '../utils';

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

export function useConversations({
  currentUserId,
  isLoadingUser,
  stateFilter,
  typeFilter,
}: UseConversationsOptions): UseConversationsResult {
  const { data: inboxState, isLoading, isError, invalidate } = useInboxState({
    stateFilter,
    typeFilter,
  });
  const { subscribe } = useMessageStream();

  // Use ref to store latest invalidate to avoid re-render loop
  const invalidateRef = useRef(invalidate);
  useEffect(() => {
    invalidateRef.current = invalidate;
  }, [invalidate]);

  // Invalidate inbox state when SSE receives a message for ANY conversation
  useEffect(() => {
    // Subscribe to all conversations using a catch-all pattern
    // Note: The current SSE implementation routes by conversation_id,
    // so we'll subscribe with a special marker and update the hook if needed
    const unsubscribe = subscribe('__global__', {
      onMessage: () => {
        // New message arrived - refresh inbox state
        invalidateRef.current();
      },
    });

    return unsubscribe;
  }, [subscribe]);

  // Transform backend ConversationSummary to frontend ConversationEntry format
  const conversations = useMemo<ConversationEntry[]>(() => {
    if (!inboxState?.conversations) return [];

    return inboxState.conversations.map((summary) => {
      // Parse name to get first/last for initials
      const nameParts = summary.other_user.name.split(' ');
      const firstName = nameParts[0] ?? '';
      const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : '';

      return {
        id: summary.id, // booking_id serves as conversation ID
        name: summary.other_user.name,
        lastMessage: summary.last_message?.preview ?? 'No messages yet',
        timestamp: summary.last_message
          ? formatRelativeTime(summary.last_message.at)
          : '',
        unread: summary.unread_count,
        avatar: getInitials(firstName, lastName),
        type: 'student' as const,
        bookingIds: [summary.id],
        primaryBookingId: summary.id,
        studentId: summary.other_user.id,
        instructorId: currentUserId ?? null,
        latestMessageAt: summary.last_message
          ? new Date(summary.last_message.at).getTime()
          : 0,
        latestMessageId: summary.last_message ? summary.id : null,
      };
    });
  }, [inboxState, currentUserId]);

  const totalUnread = inboxState?.total_unread ?? 0;
  const unreadConversationsCount = inboxState?.unread_conversations ?? 0;

  const unreadConversations = useMemo(
    () => conversations.filter((convo) => convo.unread > 0),
    [conversations]
  );

  // Dummy setConversations for compatibility with existing code
  const setConversations = () => {
    // No-op: conversations are now managed by React Query cache
    // This is here for backward compatibility
  };

  // Dummy loadConversations for compatibility
  const loadConversations = () => {
    // Trigger a refresh of inbox state
    invalidate();
  };

  return {
    conversations,
    setConversations,
    isLoading: isLoadingUser || isLoading,
    error: isError ? 'Unable to load conversations' : null,
    totalUnread,
    unreadConversations,
    unreadConversationsCount,
    loadConversations,
    stateCounts: inboxState?.state_counts,
  };
}

/**
 * useUpdateConversationState - Mutation hook for updating conversation state
 *
 * Allows archiving, trashing, or restoring conversations.
 * Automatically invalidates inbox-state queries to refresh the UI.
 */
export function useUpdateConversationState() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      bookingId,
      state,
    }: {
      bookingId: string;
      state: 'active' | 'archived' | 'trashed';
    }) => {
      const response = await fetch(
        withApiBase(`/api/v1/messages/conversations/${bookingId}/state`),
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

      return response.json();
    },
    onSuccess: () => {
      // Invalidate all inbox-state queries to refetch with updated state
      void queryClient.invalidateQueries({ queryKey: ['inbox-state'] });
    },
  });
}
