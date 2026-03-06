import type { ConversationEntry, MessageWithAttachments } from '../types';

export const syncStaleThreads = (
  conversations: ConversationEntry[],
  lastSeenTimestamp: Map<string, number>,
  staleThreads: Set<string>,
): void => {
  for (const conversation of conversations) {
    if (!conversation?.id) {
      continue;
    }
    const latest = conversation.latestMessageAt ?? 0;
    const hasSeen = lastSeenTimestamp.has(conversation.id);
    if (!hasSeen) {
      continue;
    }
    const lastSeen = lastSeenTimestamp.get(conversation.id) ?? 0;
    if (latest > lastSeen) {
      staleThreads.add(conversation.id);
    }
  }
};

export const applyDeliveryUpdate = (
  collection: MessageWithAttachments[],
  deliveredMessage: MessageWithAttachments,
  optimisticId: string,
  resolvedServerId?: string,
): MessageWithAttachments[] => {
  if (collection.length === 0) {
    return [deliveredMessage];
  }

  const hasMatch = collection.some(
    (message) => message.id === optimisticId || (resolvedServerId && message.id === resolvedServerId),
  );
  if (!hasMatch) {
    return [...collection, deliveredMessage];
  }

  return collection.map((message): MessageWithAttachments =>
    message.id === optimisticId || (resolvedServerId && message.id === resolvedServerId)
      ? {
          ...message,
          id: deliveredMessage.id,
          delivery: deliveredMessage.delivery,
          delivered_at: deliveredMessage.delivered_at,
        }
      : message,
  );
};
