export const getTimestampIsoOrEmpty = (timestamp: Date | null | undefined): string => {
  if (!(timestamp instanceof Date) || Number.isNaN(timestamp.getTime())) {
    return '';
  }

  return timestamp.toISOString();
};

type EditableChatMessage = {
  sender_id?: string | null;
  is_deleted?: boolean;
  created_at: string;
};

type ScrollContainerMetrics = {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
};

export const reloadChatView = (
  reload: () => void,
  env: string | undefined = process.env.NODE_ENV,
): void => {
  if (env !== 'test') {
    reload();
  }
};

export const triggerChatReload = (): void => {
  reloadChatView(window.location.reload.bind(window.location));
};

export const canEditChatMessage = (
  message: EditableChatMessage,
  currentUserId: string,
  nowMs: number,
  editWindowMinutes: number,
): boolean => {
  if (message.sender_id !== currentUserId) return false;
  if (message.is_deleted) return false;
  const created = new Date(message.created_at).getTime();
  const diffMinutes = (nowMs - created) / 60000;
  return diffMinutes <= editWindowMinutes;
};

export const getIsAtBottom = (
  scrollContainer: ScrollContainerMetrics | null,
  threshold = 100,
): boolean | null => {
  if (!scrollContainer) return null;
  const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
  return scrollHeight - scrollTop - clientHeight < threshold;
};

export const syncIsAtBottom = (
  scrollContainer: ScrollContainerMetrics | null,
  setIsAtBottom: (value: boolean) => void,
): boolean => {
  const nextIsAtBottom = getIsAtBottom(scrollContainer);
  if (nextIsAtBottom === null) {
    return false;
  }
  setIsAtBottom(nextIsAtBottom);
  return true;
};

type EditableChatTarget = EditableChatMessage & {
  id: string;
};

export const getEditableChatTarget = <T extends EditableChatTarget>(
  messages: T[],
  messageId: string,
  canEditMessage: (message: T) => boolean,
): T | null => {
  const target = messages.find((message) => message.id === messageId);
  if (!target || !canEditMessage(target)) {
    return null;
  }
  return target;
};

export const canHandleReaction = (processingReaction: string | null): boolean =>
  processingReaction === null;

export const editChatBubbleMessage = async <T extends EditableChatTarget>({
  messages,
  messageId,
  newContent,
  canEditMessage,
  editMessage,
}: {
  messages: T[];
  messageId: string;
  newContent: string;
  canEditMessage: (message: T) => boolean;
  editMessage: (payload: { messageId: string; data: { content: string } }) => Promise<unknown>;
}): Promise<boolean> => {
  const target = getEditableChatTarget(messages, messageId, canEditMessage);
  if (!target) {
    return false;
  }
  await editMessage({
    messageId,
    data: { content: newContent },
  });
  return true;
};

export const deleteChatBubbleMessage = async <
  T extends EditableChatTarget & {
    is_deleted?: boolean;
    content?: string | null;
  },
>({
  messages,
  messageId,
  canEditMessage,
  deleteMessage,
  updateRealtimeMessages,
  invalidateMessages,
}: {
  messages: T[];
  messageId: string;
  canEditMessage: (message: T) => boolean;
  deleteMessage: (payload: { messageId: string }) => Promise<unknown>;
  updateRealtimeMessages: (
    updater: (prev: T[]) => T[],
  ) => void;
  invalidateMessages: () => Promise<unknown> | void;
}): Promise<boolean> => {
  const target = getEditableChatTarget(messages, messageId, canEditMessage);
  if (!target) {
    return false;
  }
  await deleteMessage({ messageId });
  updateRealtimeMessages((prev) => {
    const idx = prev.findIndex((message) => message.id === messageId);
    if (idx === -1) return prev;
    const updated = [...prev];
    updated[idx] = {
      ...updated[idx]!,
      is_deleted: true,
      content: 'This message was deleted',
    };
    return updated;
  });
  await invalidateMessages();
  return true;
};

export const reactToChatBubbleMessage = async ({
  processingReaction,
  messageId,
  emoji,
  handleAddReaction,
}: {
  processingReaction: string | null;
  messageId: string;
  emoji: string;
  handleAddReaction: (messageId: string, emoji: string) => Promise<unknown>;
}): Promise<boolean> => {
  if (!canHandleReaction(processingReaction)) {
    return false;
  }
  await handleAddReaction(messageId, emoji);
  return true;
};
