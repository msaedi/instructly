import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
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
  const mutation = useJoinLessonApiV1LessonsBookingIdJoinPost({
    mutation: {
      onSuccess: (_data, variables) => {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.bookings.detail(variables.bookingId),
        });
      },
      onError: (error: unknown) => {
        const message =
          error && typeof error === 'object' && 'message' in error
            ? String((error as { message: string }).message)
            : 'Failed to join lesson';
        toast.error(message);
      },
    },
  });

  return {
    joinLesson: async (bookingId: string): Promise<VideoJoinResponse> => {
      return mutation.mutateAsync({ bookingId }) as Promise<VideoJoinResponse>;
    },
    isPending: mutation.isPending,
    error: mutation.error as Error | null,
  };
}

/**
 * Domain-friendly wrapper for the video session status query.
 * Supports polling via `pollingIntervalMs`.
 */
export function useVideoSessionStatus(
  bookingId: string,
  options?: { enabled?: boolean; pollingIntervalMs?: number },
) {
  const query = useGetVideoSessionApiV1LessonsBookingIdVideoSessionGet(bookingId, {
    query: {
      enabled: options?.enabled ?? true,
      ...(options?.pollingIntervalMs !== undefined && { refetchInterval: options.pollingIntervalMs }),
      queryKey: queryKeys.lessons.videoSession(bookingId),
    },
  });

  return {
    sessionData: (query.data as VideoSessionStatusResponse | null | undefined) ?? null,
    isLoading: query.isLoading,
    error: query.error as Error | null,
    refetch: query.refetch,
  };
}
