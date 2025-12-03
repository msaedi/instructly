// frontend/providers/UserMessageStreamProvider.tsx
'use client';

/**
 * Context provider for user-scoped SSE message stream.
 *
 * Provides single SSE connection shared across all components.
 * Components subscribe to specific conversations via conversation_id.
 *
 * Phase 4: Per-user inbox architecture
 */

import { createContext, useContext, type ReactNode } from 'react';
import { useUserMessageStream } from '@/hooks/useUserMessageStream';
import type { ConversationHandlers } from '@/types/messaging';
import { logger } from '@/lib/logger';

interface UserMessageStreamContextValue {
  isConnected: boolean;
  connectionError: string | null;
  subscribe: (
    conversationId: string,
    handlers: ConversationHandlers
  ) => () => void;
}

const UserMessageStreamContext =
  createContext<UserMessageStreamContextValue | null>(null);

export function UserMessageStreamProvider({
  children,
}: {
  children: ReactNode;
}) {
  logger.debug('[MSG-DEBUG] UserMessageStreamProvider rendering');
  const stream = useUserMessageStream();
  logger.debug('[MSG-DEBUG] UserMessageStreamProvider: hook returned', {
    isConnected: stream.isConnected,
    hasError: !!stream.connectionError,
  });

  return (
    <UserMessageStreamContext.Provider value={stream}>
      {children}
    </UserMessageStreamContext.Provider>
  );
}

export function useMessageStream() {
  const context = useContext(UserMessageStreamContext);
  if (!context) {
    throw new Error(
      'useMessageStream must be used within UserMessageStreamProvider'
    );
  }
  return context;
}
