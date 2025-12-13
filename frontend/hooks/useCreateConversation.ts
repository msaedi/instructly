/**
 * useCreateConversation - Hook for creating or getting an existing conversation
 *
 * Phase 6: Enables pre-booking messaging by creating conversations via
 * POST /api/v1/conversations endpoint.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { createConversation, conversationQueryKeys } from '@/src/api/services/conversations';
import { logger } from '@/lib/logger';

export interface CreateConversationOptions {
  /** Navigate to messages after creating (default: true) */
  navigateToMessages?: boolean;
  /** Optional initial message to send */
  initialMessage?: string;
}

export interface CreateConversationResult {
  createConversation: (
    instructorId: string,
    options?: CreateConversationOptions
  ) => Promise<{ id: string; created: boolean }>;
  isCreating: boolean;
  error: Error | null;
}

export function useCreateConversation(): CreateConversationResult {
  const router = useRouter();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async ({
      instructorId,
      initialMessage,
    }: {
      instructorId: string;
      initialMessage?: string;
    }) => {
      return createConversation(instructorId, initialMessage);
    },
    onSuccess: () => {
      // Invalidate conversations list to show the new/updated conversation
      void queryClient.invalidateQueries({ queryKey: conversationQueryKeys.all });
    },
  });

  const create = async (
    instructorId: string,
    options: CreateConversationOptions = {}
  ): Promise<{ id: string; created: boolean }> => {
    const { navigateToMessages = true, initialMessage } = options;

    try {
      const result = await mutation.mutateAsync({
        instructorId,
        ...(initialMessage !== undefined && { initialMessage }),
      });

      if (navigateToMessages) {
        // Navigate to instructor messages with conversation selected
        router.push(`/instructor/messages?conversation=${result.id}`);
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
