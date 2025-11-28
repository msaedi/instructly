/**
 * useConversations - Hook for loading and managing conversations
 *
 * Handles:
 * - Initial conversation loading from bookings
 * - Periodic refresh polling
 * - Conversation aggregation by student
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { logger } from '@/lib/logger';
import {
  fetchInstructorUpcomingBookings,
  fetchInstructorBookingsList,
} from '@/src/api/services/instructor-bookings';
import { fetchMessageHistory } from '@/src/api/services/messages';
import type { Booking } from '@/features/shared/api/types';
import type { ConversationEntry, ReadByEntry } from '../types';
import { CONVERSATION_REFRESH_INTERVAL_MS } from '../constants';
import {
  formatRelativeTime,
  getInitials,
  formatStudentName,
  getBookingActivityTimestamp,
} from '../utils';

export type UseConversationsOptions = {
  currentUserId: string | undefined;
  isLoadingUser: boolean;
};

export type UseConversationsResult = {
  conversations: ConversationEntry[];
  setConversations: React.Dispatch<React.SetStateAction<ConversationEntry[]>>;
  isLoading: boolean;
  error: string | null;
  totalUnread: number;
  unreadConversations: ConversationEntry[];
  loadConversations: () => Promise<void>;
};

export function useConversations({
  currentUserId,
  isLoadingUser,
}: UseConversationsOptions): UseConversationsResult {
  const [conversations, setConversations] = useState<ConversationEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadConversations = useCallback(async () => {
    if (isLoadingUser) return;
    if (!currentUserId) {
      setIsLoading(false);
      setConversations([]);
      return;
    }

    const buildConversationFromBooking = async (booking: Booking): Promise<ConversationEntry | null> => {
      const studentInfo = booking.student;
      const name = formatStudentName(studentInfo?.first_name, studentInfo?.last_name);
      const avatar = getInitials(studentInfo?.first_name, studentInfo?.last_name);
      const studentId = booking.student_id ?? (studentInfo as { id?: string } | null)?.id ?? null;
      const conversationId = studentId ? `student-${studentId}` : booking.id;

      const baseDate = getBookingActivityTimestamp(booking);
      const fallbackActivity = baseDate ? new Date(baseDate).getTime() : Date.now();

      let lastMessage = 'No messages yet';
      let timestamp = formatRelativeTime(baseDate);
      let latestMessageAt = fallbackActivity;
      let unread = 0;
      let latestMessageId: string | null = null;

      try {
        const history = await fetchMessageHistory(booking.id, { limit: 1, offset: 0 });
        const latest = history.messages?.[history.messages.length - 1];
        if (latest) {
          lastMessage = latest.content ?? '';
          timestamp = formatRelativeTime(latest.created_at);
          latestMessageAt = latest.created_at ? new Date(latest.created_at).getTime() : fallbackActivity;
          latestMessageId = latest.id ?? null;

          if (latest.sender_id && latest.sender_id !== currentUserId) {
            const readByEntries = (latest.read_by ?? []) as ReadByEntry[];
            const hasRead = readByEntries.some((entry) => entry.user_id === currentUserId && !!entry.read_at);
            if (!hasRead) {
              unread = 1;
            }
          }
        }
      } catch (err) {
        logger.warn('Failed to fetch latest message for booking', { bookingId: booking.id, error: err });
      }

      return {
        id: conversationId,
        name,
        lastMessage,
        timestamp,
        unread,
        avatar,
        type: 'student',
        bookingIds: [booking.id],
        primaryBookingId: booking.id,
        studentId,
        instructorId: booking.instructor_id ?? null,
        latestMessageAt,
        latestMessageId,
      };
    };

    setIsLoading(true);
    setError(null);

    try {
      const results = await Promise.allSettled([
        fetchInstructorUpcomingBookings({ per_page: 25 }),
        fetchInstructorBookingsList({ per_page: 25 }),
      ]);

      const bookingMap = new Map<string, Booking>();
      for (const result of results) {
        if (result.status === 'fulfilled') {
          result.value.items.forEach((booking) => {
            if (booking.instructor_id !== currentUserId) {
              return;
            }
            bookingMap.set(booking.id, booking);
          });
        } else {
          logger.warn('Booking fetch failed for conversations', { error: result.reason });
        }
      }

      const bookings = Array.from(bookingMap.values());
      bookings.sort((a, b) => {
        const extractTime = (bk: Booking) => {
          const base = getBookingActivityTimestamp(bk);
          return base ? new Date(base).getTime() : 0;
        };
        return extractTime(b) - extractTime(a);
      });

      const conversationsList: ConversationEntry[] = [];
      for (const booking of bookings) {
        const entry = await buildConversationFromBooking(booking);
        if (entry) {
          conversationsList.push(entry);
        }
      }

      // Aggregate conversations by student
      const aggregated = new Map<string, ConversationEntry>();
      for (const entry of conversationsList) {
        const existing = aggregated.get(entry.id);
        if (!existing) {
          aggregated.set(entry.id, entry);
          continue;
        }
        const latestIsExisting = existing.latestMessageAt >= entry.latestMessageAt;
        const latestEntry = latestIsExisting ? existing : entry;
        const mergedBookingIds = [
          ...(latestIsExisting ? existing.bookingIds : entry.bookingIds),
          ...(latestIsExisting ? entry.bookingIds : existing.bookingIds),
        ];
        const uniqueBookingIds = Array.from(new Set(mergedBookingIds));
        aggregated.set(entry.id, {
          ...latestEntry,
          bookingIds: uniqueBookingIds,
          primaryBookingId: latestIsExisting
            ? existing.primaryBookingId ?? entry.primaryBookingId
            : entry.primaryBookingId ?? existing.primaryBookingId,
          unread: (existing.unread ?? 0) + (entry.unread ?? 0),
          latestMessageAt: Math.max(existing.latestMessageAt, entry.latestMessageAt),
          latestMessageId: latestEntry.latestMessageId ?? existing.latestMessageId ?? null,
        });
      }

      const mergedConversations = Array.from(aggregated.values());
      mergedConversations.sort((a, b) => b.latestMessageAt - a.latestMessageAt);
      setConversations(mergedConversations);
    } catch (err) {
      logger.error('Failed to load conversations', { error: err });
      setConversations([]);
      setError('Unable to load conversations');
    } finally {
      setIsLoading(false);
    }
  }, [currentUserId, isLoadingUser]);

  // Initial load
  useEffect(() => {
    if (isLoadingUser) return;
    void loadConversations();
  }, [loadConversations, isLoadingUser]);

  // Periodic refresh
  useEffect(() => {
    if (isLoadingUser || !currentUserId) return;

    const intervalId = setInterval(() => {
      void loadConversations();
    }, CONVERSATION_REFRESH_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, [loadConversations, isLoadingUser, currentUserId]);

  const totalUnread = useMemo(
    () => conversations.reduce((sum, convo) => sum + (convo.unread ?? 0), 0),
    [conversations]
  );

  const unreadConversations = useMemo(
    () => conversations.filter((convo) => (convo.unread ?? 0) > 0),
    [conversations]
  );

  return {
    conversations,
    setConversations,
    isLoading,
    error,
    totalUnread,
    unreadConversations,
    loadConversations,
  };
}
