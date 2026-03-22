/**
 * useCreateConversation - Hook for creating or getting an existing conversation
 *
 * Phase 6: Enables pre-booking messaging by creating conversations via
 * POST /api/v1/conversations endpoint.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { usePathname, useRouter } from 'next/navigation';
import { createConversation, conversationQueryKeys } from '@/src/api/services/conversations';
import { logger } from '@/lib/logger';

export interface CreateConversationOptions {
  /** Navigate to messages after creating (default: true) */
  navigateToMessages?: boolean;
  /** Optional initial message to send */
  initialMessage?: string;
  /** Optional caller context for deciding the destination route */
  viewerContext?: 'instructor' | 'student';
}

export interface CreateConversationResult {
  createConversation: (
    otherUserId: string,
    options?: CreateConversationOptions
  ) => Promise<{ id: string; created: boolean }>;
  isCreating: boolean;
  error: Error | null;
}

function buildConversationDestination(
  pathname: string | null,
  viewerContext: 'instructor' | 'student' | undefined,
  conversationId: string,
): string {
  const normalizedContext = viewerContext;
  const isInstructorRoute = pathname?.startsWith('/instructor') ?? false;
  const isStudentRoute = pathname?.startsWith('/student') ?? false;
  const useStudentMessages = normalizedContext === 'student'
    || isStudentRoute
    || (!normalizedContext && !isInstructorRoute);

  if (useStudentMessages) {
    const nextParams = new URLSearchParams({
      conversation: conversationId,
    });
    return `/student/messages?${nextParams.toString()}`;
  }

  const nextParams = new URLSearchParams({
    panel: 'messages',
    conversation: conversationId,
  });
  return `/instructor/dashboard?${nextParams.toString()}`;
}

export function useCreateConversation(): CreateConversationResult {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async ({
      otherUserId,
      initialMessage,
    }: {
      otherUserId: string;
      initialMessage?: string;
    }) => {
      return createConversation(otherUserId, initialMessage);
    },
    onSuccess: () => {
      // Invalidate conversations list to show the new/updated conversation
      void queryClient.invalidateQueries({ queryKey: conversationQueryKeys.all });
    },
  });

  const create = async (
    otherUserId: string,
    options: CreateConversationOptions = {}
  ): Promise<{ id: string; created: boolean }> => {
    const { navigateToMessages = true, initialMessage, viewerContext } = options;

    try {
      const result = await mutation.mutateAsync({
        otherUserId,
        ...(initialMessage !== undefined && { initialMessage }),
      });

      if (navigateToMessages) {
        router.push(buildConversationDestination(pathname, viewerContext, result.id));
      }

      logger.debug('Conversation created/retrieved', {
        conversationId: result.id,
        created: result.created,
        navigated: navigateToMessages,
      });

      return result;
    } catch (error) {
      logger.error('Failed to create conversation', error as Error);
      throw error;
    }
  };

  return {
    createConversation: create,
    isCreating: mutation.isPending,
    error: mutation.error,
  };
}
