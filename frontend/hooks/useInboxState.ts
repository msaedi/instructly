import { useState, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { usePageVisibility } from './usePageVisibility';
import { useAuthStatus } from './queries/useAuth';
import { withApiBase } from '@/lib/apiBase';

// Custom error class for 304 Not Modified responses
class NotModifiedError extends Error {
  constructor() {
    super('Not Modified');
    this.name = 'NotModifiedError';
  }
}

// Types matching backend response
export interface OtherUserInfo {
  id: string;
  name: string;
  avatar_url?: string | null;
}

export interface LastMessageInfo {
  preview: string;
  at: string;
  is_mine: boolean;
}

export interface ConversationSummary {
  id: string; // booking_id
  other_user: OtherUserInfo;
  unread_count: number;
  last_message: LastMessageInfo | null;
}

export interface InboxState {
  conversations: ConversationSummary[];
  total_unread: number;
  unread_conversations: number;
}

// Polling intervals
const ACTIVE_INTERVAL = 5000; // 5 seconds when activity detected
const IDLE_INTERVAL = 15000; // 15 seconds when quiet
const ACTIVITY_THRESHOLD = 3; // Number of unchanged polls before going idle

// Query key for cache management
export const inboxStateQueryKey = ['inbox-state'] as const;

export function useInboxState() {
  const { isAuthenticated } = useAuthStatus();
  const isVisible = usePageVisibility();
  const queryClient = useQueryClient();

  // Track ETag for caching
  const etagRef = useRef<string | null>(null);

  // Track consecutive unchanged responses for adaptive polling
  const unchangedCountRef = useRef(0);
  const [isActive, setIsActive] = useState(true);

  // Fetch function with ETag support
  const fetchInboxState = useCallback(async (): Promise<InboxState> => {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // Include ETag if we have one
    if (etagRef.current) {
      headers['If-None-Match'] = etagRef.current;
    }

    const response = await fetch(withApiBase('/api/v1/messages/inbox-state'), {
      method: 'GET',
      headers,
      credentials: 'include',
    });

    // 304 Not Modified - throw to tell React Query to keep previous data
    if (response.status === 304) {
      unchangedCountRef.current += 1;

      // Switch to idle polling after threshold
      if (unchangedCountRef.current >= ACTIVITY_THRESHOLD) {
        setIsActive(false);
      }

      // Throw special error that we catch in React Query config
      throw new NotModifiedError();
    }

    if (!response.ok) {
      throw new Error(`Failed to fetch inbox state: ${response.status}`);
    }

    // Store new ETag
    const newEtag = response.headers.get('ETag');
    if (newEtag) {
      etagRef.current = newEtag;
    }

    // Activity detected - reset counter and go active
    unchangedCountRef.current = 0;
    setIsActive(true);

    return response.json();
  }, []);

  // React Query with adaptive polling
  const query = useQuery({
    queryKey: inboxStateQueryKey,
    queryFn: fetchInboxState,
    enabled: isAuthenticated && isVisible,
    refetchInterval: () => {
      if (!isVisible) return false; // Don't poll when hidden
      return isActive ? ACTIVE_INTERVAL : IDLE_INTERVAL;
    },
    refetchOnWindowFocus: true,
    staleTime: ACTIVE_INTERVAL, // Consider data stale after interval
    retry: (failureCount, error) => {
      // Don't retry on 304
      if (error instanceof NotModifiedError) return false;
      return failureCount < 3;
    },
    // Keep previous data on 304 error
    placeholderData: (previousData) => previousData,
  });

  // Manual refresh function (for immediate updates)
  const refresh = useCallback(() => {
    // Reset to active polling
    setIsActive(true);
    unchangedCountRef.current = 0;
    // Clear ETag to force full fetch
    etagRef.current = null;
    void queryClient.invalidateQueries({ queryKey: inboxStateQueryKey });
  }, [queryClient]);

  // Invalidate cache (call when SSE receives new message for non-active conversation)
  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: inboxStateQueryKey });
  }, [queryClient]);

  return {
    data: query.data ?? undefined,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    isActive, // Whether polling at active rate
    refresh, // Force immediate refresh
    invalidate, // Invalidate cache
  };
}
