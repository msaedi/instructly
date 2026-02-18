import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import type { VideoJoinResponse, VideoSessionStatusResponse } from '@/features/shared/api/types';
import {
  useJoinLessonApiV1LessonsBookingIdJoinPost,
  useGetVideoSessionApiV1LessonsBookingIdVideoSessionGet,
} from '@/src/api/generated/lessons-v1/lessons-v1';

/**
 * Domain-friendly wrapper for the join-lesson mutation.
 * Invalidates the booking detail cache on success.
 */
export function useJoinLesson() {
  const queryClient = useQueryClient();
  const mutation = useJoinLessonApiV1LessonsBookingIdJoinPost<Error>({
    mutation: {
      onSuccess: (_data, variables) => {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.bookings.detail(variables.bookingId),
        });
      },
    },
  });

  return {
    joinLesson: async (bookingId: string): Promise<VideoJoinResponse> => {
      return mutation.mutateAsync({ bookingId });
    },
    isPending: mutation.isPending,
    error: mutation.error ?? null,
  };
}

/**
 * Domain-friendly wrapper for the video session status query.
 * Supports polling via `pollingIntervalMs`.
 */
export function useVideoSessionStatus(
  bookingId: string,
  options?: {
    enabled?: boolean;
    pollingIntervalMs?: number;
    stopPollingWhenEnded?: boolean;
  },
) {
  const refetchInterval =
    options?.pollingIntervalMs !== undefined
      ? (query: { state: { data?: VideoSessionStatusResponse | null } }) => {
          if (options.stopPollingWhenEnded && query.state.data?.session_ended_at) {
            return false;
          }
          return options.pollingIntervalMs;
        }
      : undefined;

  const query = useGetVideoSessionApiV1LessonsBookingIdVideoSessionGet<
    VideoSessionStatusResponse | null,
    Error
  >(bookingId, {
    query: {
      enabled: options?.enabled ?? true,
      ...(refetchInterval !== undefined && { refetchInterval }),
      queryKey: queryKeys.lessons.videoSession(bookingId),
    },
  });

  return {
    sessionData: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error ?? null,
    refetch: query.refetch,
  };
}
