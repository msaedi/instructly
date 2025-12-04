/**
 * useMessageThread - Hook for managing message thread state
 *
 * Handles:
 * - Current thread messages
 * - Messages cache by thread
 * - Archived/trash message separation
 * - Thread loading from API
 * - Archive/delete operations
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { logger } from '@/lib/logger';
import { queryKeys } from '@/src/api/queryKeys';
import {
  useMessageHistory,
  sendMessageImperative,
  markMessagesAsReadImperative,
} from '@/src/api/services/messages';
import type { MessageResponse } from '@/src/api/generated/instructly.schemas';
import type {
  ConversationEntry,
  MessageWithAttachments,
  MessageDisplayMode,
  MessageAttachment,
  SSEMessageWithOwnership,
} from '../types';
import { COMPOSE_THREAD_ID } from '../constants';
import { mapMessageFromResponse, computeUnreadFromMessages, formatRelativeTimestamp } from '../utils';

export type UseMessageThreadOptions = {
  currentUserId: string | undefined;
  conversations: ConversationEntry[];
  setConversations: React.Dispatch<React.SetStateAction<ConversationEntry[]>>;
};

export type UseMessageThreadResult = {
  threadMessages: MessageWithAttachments[];
  messagesByThread: Record<string, MessageWithAttachments[]>;
  archivedMessagesByThread: Record<string, MessageWithAttachments[]>;
  trashMessagesByThread: Record<string, MessageWithAttachments[]>;
  loadThreadMessages: (
    selectedChat: string,
    activeConversation: ConversationEntry | null,
    messageDisplay: MessageDisplayMode
  ) => void;
  handleSSEMessage: (
    message: SSEMessageWithOwnership,
    selectedChat: string,
    activeConversation: ConversationEntry
  ) => void;
  handleSendMessage: (params: {
    selectedChat: string | null;
    messageText: string;
    pendingAttachments: File[];
    composeRecipient: ConversationEntry | null;
    conversations: ConversationEntry[];
    getPrimaryBookingId: (threadId: string | null) => string | null;
    onSuccess: (targetThreadId: string, switchingFromCompose: boolean) => void;
  }) => Promise<void>;
  handleArchiveConversation: (conversationId: string) => void;
  handleDeleteConversation: (conversationId: string) => void;
  setThreadMessagesForDisplay: (
    selectedChat: string,
    messageDisplay: MessageDisplayMode
  ) => void;
  updateThreadMessage: (
    messageId: string,
    updater: (message: MessageWithAttachments) => MessageWithAttachments
  ) => void;
  invalidateConversationCache: (conversationId: string) => void;
};

export function useMessageThread({
  currentUserId,
  conversations: _conversations,
  setConversations,
}: UseMessageThreadOptions): UseMessageThreadResult {
  const HISTORY_LIMIT = 100;
  const HISTORY_OFFSET = 0;
  const queryClient = useQueryClient();

  // Thread messages state
  const [threadMessages, setThreadMessages] = useState<MessageWithAttachments[]>([]);
  const [messagesByThread, setMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});
  const [archivedMessagesByThread, setArchivedMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});
  const [trashMessagesByThread, setTrashMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});
  const [historyTarget, setHistoryTarget] = useState<{
    threadId: string;
    conversation: ConversationEntry;
  } | null>(null);
  const lastHistoryAppliedRef = useRef<string | null>(null);
  const lastSeenTimestampRef = useRef<Map<string, number>>(new Map());
  const staleThreadsRef = useRef<Set<string>>(new Set());

  // Refs for current state access in callbacks
  const messagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const archivedMessagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const trashMessagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const threadMessagesRef = useRef<MessageWithAttachments[]>([]);
  const markedReadThreadsRef = useRef<Map<string, number>>(new Map());
  const conversationsRef = useRef<ConversationEntry[]>(_conversations ?? []);

  useEffect(() => {
    conversationsRef.current = _conversations ?? [];
  }, [_conversations]);

  // Keep refs in sync
  useEffect(() => {
    messagesByThreadRef.current = messagesByThread;
  }, [messagesByThread]);
  useEffect(() => {
    archivedMessagesByThreadRef.current = archivedMessagesByThread;
  }, [archivedMessagesByThread]);
  useEffect(() => {
    trashMessagesByThreadRef.current = trashMessagesByThread;
  }, [trashMessagesByThread]);
  useEffect(() => {
    threadMessagesRef.current = threadMessages;
  }, [threadMessages]);

  // Helper: update last seen timestamp and clear stale flag
  const updateLastSeenTimestamp = useCallback((threadId: string, timestampMs: number | undefined) => {
    if (!threadId || !timestampMs || Number.isNaN(timestampMs)) return;
    lastSeenTimestampRef.current.set(threadId, timestampMs);
    staleThreadsRef.current.delete(threadId);
  }, []);

  // When inbox-state derived conversations update, mark stale threads whose latestMessageAt advanced
  useEffect(() => {
    if (!conversationsRef.current) return;
    for (const conv of conversationsRef.current) {
      if (!conv?.id) continue;
      const latest = conv.latestMessageAt ?? 0;
      const hasSeen = lastSeenTimestampRef.current.has(conv.id);
      if (!hasSeen) continue; // unseen threads will fetch on first view
      const lastSeen = lastSeenTimestampRef.current.get(conv.id) ?? 0;
      if (latest > lastSeen) {
        staleThreadsRef.current.add(conv.id);
      }
    }
  }, [_conversations]);

  const historyBookingId = historyTarget?.conversation.primaryBookingId ?? '';
  const {
    data: historyData,
    error: historyError,
  } = useMessageHistory(historyBookingId, HISTORY_LIMIT, HISTORY_OFFSET, Boolean(historyBookingId));

  // Set thread messages for current display mode
  const setThreadMessagesForDisplay = useCallback((
    selectedChat: string,
    messageDisplay: MessageDisplayMode
  ) => {
    if (!selectedChat || selectedChat === COMPOSE_THREAD_ID) return;
    if (messageDisplay === 'archived') {
      setThreadMessages(archivedMessagesByThreadRef.current[selectedChat] ?? []);
    } else if (messageDisplay === 'trash') {
      setThreadMessages(trashMessagesByThreadRef.current[selectedChat] ?? []);
    } else {
      setThreadMessages(messagesByThreadRef.current[selectedChat] ?? []);
    }
  }, []);

  // Load thread messages from API
  const loadThreadMessages = useCallback((
    selectedChat: string,
    activeConversation: ConversationEntry | null,
    _messageDisplay: MessageDisplayMode
  ) => {
    if (!selectedChat || selectedChat === COMPOSE_THREAD_ID || !activeConversation || !currentUserId) return;

    const bookingId = activeConversation.primaryBookingId;
    if (!bookingId) return;

    const cached = messagesByThreadRef.current[selectedChat];
    const hasCache = Boolean(cached && cached.length > 0);
    const isStale = staleThreadsRef.current.has(selectedChat);
    const shouldFetchHistory = isStale || !hasCache;

    // Show any cached thread immediately while React Query fetches fresh data
    const existing = messagesByThreadRef.current[selectedChat];
    if (existing) {
      setThreadMessages(existing);
    } else {
      setThreadMessages([]);
    }

    // Initialize last-seen to current latestMessageAt so inbox polling doesn't mark stale immediately
    if (!lastSeenTimestampRef.current.has(selectedChat)) {
      const initialTs = activeConversation.latestMessageAt ?? 0;
      if (initialTs > 0) {
        lastSeenTimestampRef.current.set(selectedChat, initialTs);
      }
    }

    if (shouldFetchHistory) {
      staleThreadsRef.current.delete(selectedChat);
      setHistoryTarget({ threadId: selectedChat, conversation: activeConversation });
    } else if (!hasCache) {
      // If no cache but also not stale (shouldn't happen), force fetch
      setHistoryTarget({ threadId: selectedChat, conversation: activeConversation });
    }

    // Proactively mark as read on first view of this conversation to avoid duplicate effects
    const lastMarked = markedReadThreadsRef.current.get(bookingId);
    if (lastMarked === undefined) {
      markedReadThreadsRef.current.set(bookingId, 0);
      void markMessagesAsReadImperative({ booking_id: bookingId }).catch(() => {
        markedReadThreadsRef.current.delete(bookingId);
      });
    }
  }, [currentUserId]);

  // When React Query returns history data, merge it into local state and handle read status
  useEffect(() => {
    if (!historyTarget || !historyData || !currentUserId) return;

    const { threadId, conversation } = historyTarget;
    const messages = historyData.messages || [];

    // Guard against re-processing identical history payloads (prevents render loops in tests)
    const lastMessageId = messages[messages.length - 1]?.id ?? 'none';
    const dedupeKey = `${threadId}:${messages.length}:${lastMessageId}`;
    if (lastHistoryAppliedRef.current === dedupeKey) {
      return;
    }
    lastHistoryAppliedRef.current = dedupeKey;

    const mappedMessages = messages.map((msg) =>
      mapMessageFromResponse(msg, conversation, currentUserId)
    );

    // Merge history with any SSE-only messages we already have
    const existing = messagesByThreadRef.current[threadId] || [];
    const historyIds = new Set(mappedMessages.map((m) => m.id));
    const sseOnlyMessages = existing.filter((m) => !historyIds.has(m.id));

    const mergedMessages = [...mappedMessages, ...sseOnlyMessages].sort((a, b) => {
      const timeA = new Date(a.createdAt || '').getTime();
      const timeB = new Date(b.createdAt || '').getTime();
      return timeA - timeB;
    });

    setMessagesByThread((prev) => ({ ...prev, [threadId]: mergedMessages }));
    setThreadMessages(mergedMessages);

    // Track last seen message timestamp for staleness checks
    const lastTimestamp = mergedMessages.length > 0
      ? new Date(mergedMessages[mergedMessages.length - 1]?.createdAt || '').getTime()
      : (conversation.latestMessageAt ?? undefined);
    updateLastSeenTimestamp(threadId, lastTimestamp);

    // Update conversation unread count
    const unreadCount = computeUnreadFromMessages(messages, conversation, currentUserId);
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === threadId ? { ...conv, unread: unreadCount } : conv
      )
    );

    // Mark messages as read for this booking when needed
    const bookingId = conversation.primaryBookingId;
    if (bookingId) {
      const lastCount = markedReadThreadsRef.current.get(bookingId);
      const shouldMarkRead = unreadCount > 0 || lastCount === undefined;

      if (shouldMarkRead) {
        markedReadThreadsRef.current.set(bookingId, unreadCount);
        markMessagesAsReadImperative({ booking_id: bookingId })
          .then(() => {
            setConversations((prev) =>
              prev.map((conv) =>
                conv.id === threadId ? { ...conv, unread: 0 } : conv
              )
            );
            markedReadThreadsRef.current.set(bookingId, 0);
          })
          .catch(() => {
            // Revert the last known count on failure
            if (lastCount !== undefined) {
              markedReadThreadsRef.current.set(bookingId, lastCount);
            } else {
              markedReadThreadsRef.current.delete(bookingId);
            }
          });
      } else {
        markedReadThreadsRef.current.set(bookingId, 0);
      }
    }
  }, [historyData, historyTarget, currentUserId, setConversations, updateLastSeenTimestamp]);

  useEffect(() => {
    if (historyError && historyTarget) {
      logger.error('Failed to fetch messages for conversation', {
        conversationId: historyTarget.threadId,
        error: historyError,
      });
    }
  }, [historyError, historyTarget]);

  // Handle SSE message
  const handleSSEMessage = useCallback((
    message: SSEMessageWithOwnership,
    selectedChat: string,
    activeConversation: ConversationEntry
  ) => {
    if (!currentUserId) return;

    const mappedMessage = mapMessageFromResponse(
      message as MessageResponse,
      activeConversation,
      currentUserId
    );

    // For own messages: update existing message with new fields (e.g., delivered_at)
    // For other messages: add new message to thread
    const isOwnMessage = message.is_mine === true || message.sender_id === currentUserId;

    // Add or update in current thread
    setMessagesByThread((prev) => {
      const existing = prev[selectedChat] ?? [];
      const existingIndex = existing.findIndex((m) => m.id === mappedMessage.id);
      if (existingIndex !== -1) {
        // Update existing message (e.g., delivered_at for own messages)
        const updated = [...existing];
        updated[existingIndex] = {
          ...updated[existingIndex]!,
          delivered_at: mappedMessage.delivered_at ?? updated[existingIndex]!.delivered_at,
        };
        return { ...prev, [selectedChat]: updated };
      }
      // Only add new messages from other users
      if (isOwnMessage) return prev;
      return { ...prev, [selectedChat]: [...existing, mappedMessage] };
    });

    setThreadMessages((prev) => {
      const existingIndex = prev.findIndex((m) => m.id === mappedMessage.id);
      if (existingIndex !== -1) {
        // Update existing message
        const updated = [...prev];
        updated[existingIndex] = {
          ...updated[existingIndex]!,
          delivered_at: mappedMessage.delivered_at ?? updated[existingIndex]!.delivered_at,
        };
        updateLastSeenTimestamp(selectedChat, new Date(mappedMessage.createdAt || '').getTime());
        return updated;
      }
      // Only add new messages from other users
      if (isOwnMessage) return prev;
      const next = [...prev, mappedMessage];
      updateLastSeenTimestamp(selectedChat, new Date(mappedMessage.createdAt || '').getTime());
      return next;
    });

    // Update conversation preview
    setConversations((prev) =>
      prev.map((conv) => {
        if (conv.id !== selectedChat) return conv;
        return {
          ...conv,
          lastMessage: mappedMessage.text,
          timestamp: formatRelativeTimestamp(mappedMessage.createdAt),
          latestMessageAt: mappedMessage.createdAt
            ? new Date(mappedMessage.createdAt).getTime()
            : Date.now(),
          latestMessageId: mappedMessage.id,
          unread: 0,
        };
      })
    );

    // Invalidate unread count
    void queryClient.invalidateQueries({ queryKey: queryKeys.messages.unreadCount });

    // If we're viewing this thread and received a message from the other user, mark as read server-side
    if (!isOwnMessage && activeConversation.primaryBookingId) {
      markedReadThreadsRef.current.set(activeConversation.primaryBookingId, 0);
      void markMessagesAsReadImperative({ booking_id: activeConversation.primaryBookingId }).catch((err) => {
        logger.warn('[MSG-DEBUG] Failed to mark messages as read from SSE handler', {
          bookingId: activeConversation.primaryBookingId,
          error: err instanceof Error ? err.message : err,
        });
      });
    }
  }, [currentUserId, setConversations, queryClient, updateLastSeenTimestamp]);

  // Send message
  const handleSendMessage = useCallback(async ({
    selectedChat,
    messageText,
    pendingAttachments,
    composeRecipient,
    conversations: _unusedConversations,
    getPrimaryBookingId,
    onSuccess,
  }: {
    selectedChat: string | null;
    messageText: string;
    pendingAttachments: File[];
    composeRecipient: ConversationEntry | null;
    conversations: ConversationEntry[];
    getPrimaryBookingId: (threadId: string | null) => string | null;
    onSuccess: (targetThreadId: string, switchingFromCompose: boolean) => void;
  }) => {
    const trimmed = messageText.trim();
    const hasAttachments = pendingAttachments.length > 0;
    if (!trimmed && !hasAttachments) return;
    if (!currentUserId) return;

    let targetThreadId = selectedChat;
    let switchingFromCompose = false;

    if (!targetThreadId || targetThreadId === COMPOSE_THREAD_ID) {
      if (!composeRecipient) return;
      targetThreadId = composeRecipient.id;
      switchingFromCompose = true;
    }

    const shouldUpdateVisibleThread = switchingFromCompose || targetThreadId === selectedChat;

    // Create optimistic message
    const optimisticId = `local-${Date.now()}`;
    const optimistic: MessageWithAttachments = {
      id: optimisticId,
      text: trimmed,
      sender: 'instructor',
      timestamp: 'Just now',
      delivery: { status: 'sending' },
      isArchived: false,
      createdAt: new Date().toISOString(),
      senderId: currentUserId,
    };

    // Add attachments if any
    if (hasAttachments) {
      const attachmentPayload: MessageAttachment[] = pendingAttachments.map((file) => ({
        name: file.name,
        type: file.type,
        dataUrl: '',
      }));
      optimistic.attachments = attachmentPayload;
    }

    // Update local state optimistically
    const existingThread = messagesByThreadRef.current[targetThreadId] || [];
    const updatedThread = [...existingThread, optimistic];

    setMessagesByThread((prev) => ({ ...prev, [targetThreadId]: updatedThread }));
    if (shouldUpdateVisibleThread) {
      setThreadMessages(updatedThread);
    }

    // Update conversation list
    setConversations((prev) => {
      let found = false;
      const mapped = prev.map((c) => {
        if (c.id !== targetThreadId) return c;
        found = true;
        return {
          ...c,
          lastMessage: trimmed || (hasAttachments ? `Sent ${pendingAttachments.length} attachment(s)` : c.lastMessage),
          timestamp: 'Just now',
          unread: 0,
          latestMessageAt: Date.now(),
        };
      });

      const nextList = found
        ? mapped
        : [
            ...mapped,
            {
              id: targetThreadId,
              name: composeRecipient?.name ?? 'Conversation',
              lastMessage: trimmed,
              timestamp: 'Just now',
              unread: 0,
              avatar: composeRecipient?.avatar ?? '??',
              type: 'student' as const,
              bookingIds: composeRecipient?.bookingIds ?? [],
              primaryBookingId: composeRecipient?.primaryBookingId ?? null,
              studentId: composeRecipient?.studentId ?? null,
              instructorId: composeRecipient?.instructorId ?? currentUserId,
              latestMessageAt: Date.now(),
              latestMessageId: optimisticId,
            },
          ];

      return nextList.sort((a, b) => b.latestMessageAt - a.latestMessageAt);
    });

    // Send to server
    const bookingIdTarget = getPrimaryBookingId(targetThreadId);
    let resolvedServerId: string | undefined;
    let deliveredAtFromBackend: string | null = null;
    const optimisticTimestamp = new Date().getTime();
    updateLastSeenTimestamp(targetThreadId, optimisticTimestamp);

    try {
      if (bookingIdTarget) {
        const composedForServer = trimmed || (hasAttachments
          ? pendingAttachments.map((file) => `[Attachment] ${file.name}`).join('\n')
          : '');
        const res = await sendMessageImperative({
          booking_id: bookingIdTarget,
          content: composedForServer,
        });
        resolvedServerId = res?.message?.id ?? undefined;
        // Store delivered_at from backend response
        deliveredAtFromBackend = res?.message?.delivered_at ?? null;
      }
    } catch (error) {
      logger.warn('Failed to persist instructor message', { error });
    }

    // Update with delivered status
    const deliveredAt = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const deliveredMessage: MessageWithAttachments = {
      ...optimistic,
      id: resolvedServerId ?? optimisticId,
      delivery: { status: 'delivered', timeLabel: deliveredAt },
      // Add delivered_at field from backend response (Bug #4 fix)
      delivered_at: deliveredAtFromBackend,
    };

    const applyDeliveryUpdate = (collection: MessageWithAttachments[]): MessageWithAttachments[] => {
      if (!collection || collection.length === 0) return [deliveredMessage];
      const hasMatch = collection.some((m) => m.id === optimisticId || (resolvedServerId && m.id === resolvedServerId));
      if (!hasMatch) return [...collection, deliveredMessage];
      return collection.map((m): MessageWithAttachments =>
        m.id === optimisticId || (resolvedServerId && m.id === resolvedServerId)
          ? { ...m, id: deliveredMessage.id, delivery: deliveredMessage.delivery, delivered_at: deliveredMessage.delivered_at }
          : m
      );
    };

    if (shouldUpdateVisibleThread) {
      setThreadMessages((prev) => applyDeliveryUpdate(prev));
    }
    setMessagesByThread((prev) => ({
      ...prev,
      [targetThreadId]: applyDeliveryUpdate(prev[targetThreadId] || []),
    }));

    onSuccess(targetThreadId, switchingFromCompose);
  }, [currentUserId, setConversations, updateLastSeenTimestamp]);

  // Archive conversation - moves all active messages to archived
  const handleArchiveConversation = useCallback((conversationId: string) => {
    if (conversationId === COMPOSE_THREAD_ID) return;

    const existingActive = messagesByThreadRef.current[conversationId] ?? [];
    const existingArchived = archivedMessagesByThreadRef.current[conversationId] ?? [];

    // Move all active messages to archived
    const archivedMessages = existingActive.map((msg) => ({
      ...msg,
      isArchived: true,
      isTrashed: false,
    }));
    const nextArchived = [...existingArchived, ...archivedMessages]
      .sort((a, b) => {
        const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
        const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
        return aTime - bTime;
      });

    setMessagesByThread((prev) => ({ ...prev, [conversationId]: [] }));
    setArchivedMessagesByThread((prev) => ({ ...prev, [conversationId]: nextArchived }));
    setThreadMessages([]);

    logger.info('Archived conversation', { conversationId, messageCount: existingActive.length });
  }, []);

  // Delete conversation - moves all messages to trash
  const handleDeleteConversation = useCallback((conversationId: string) => {
    if (conversationId === COMPOSE_THREAD_ID) return;

    const existingActive = messagesByThreadRef.current[conversationId] ?? [];
    const existingArchived = archivedMessagesByThreadRef.current[conversationId] ?? [];
    const existingTrash = trashMessagesByThreadRef.current[conversationId] ?? [];

    // Move all messages (active + archived) to trash
    const allMessages = [...existingActive, ...existingArchived];
    const trashedMessages = allMessages.map((msg) => ({
      ...msg,
      isArchived: false,
      isTrashed: true,
    }));
    const nextTrash = [...existingTrash, ...trashedMessages]
      .sort((a, b) => {
        const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
        const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
        return aTime - bTime;
      });

    setMessagesByThread((prev) => ({ ...prev, [conversationId]: [] }));
    setArchivedMessagesByThread((prev) => ({ ...prev, [conversationId]: [] }));
    setTrashMessagesByThread((prev) => ({ ...prev, [conversationId]: nextTrash }));
    setThreadMessages([]);

    logger.info('Deleted conversation', { conversationId, messageCount: allMessages.length });
  }, []);

  // Update a specific message (e.g., for reaction updates)
  const updateThreadMessage = useCallback((
    messageId: string,
    updater: (message: MessageWithAttachments) => MessageWithAttachments
  ) => {
    // Update in all state objects
    setThreadMessages((prev) => prev.map((msg) => msg.id === messageId ? updater(msg) : msg));
    setMessagesByThread((prev) => {
      const updated = { ...prev };
      for (const threadId in updated) {
        updated[threadId] = updated[threadId]?.map((msg) => msg.id === messageId ? updater(msg) : msg) ?? [];
      }
      return updated;
    });
    setArchivedMessagesByThread((prev) => {
      const updated = { ...prev };
      for (const threadId in updated) {
        updated[threadId] = updated[threadId]?.map((msg) => msg.id === messageId ? updater(msg) : msg) ?? [];
      }
      return updated;
    });
    setTrashMessagesByThread((prev) => {
      const updated = { ...prev };
      for (const threadId in updated) {
        updated[threadId] = updated[threadId]?.map((msg) => msg.id === messageId ? updater(msg) : msg) ?? [];
      }
      return updated;
    });
  }, []);

  // Invalidate conversation cache to force refetch on next view
  const invalidateConversationCache = useCallback((conversationId: string) => {
    const conversation = conversationsRef.current.find((c) => c.id === conversationId);
    const bookingId = conversation?.primaryBookingId;
    if (!bookingId) return;

    void queryClient.invalidateQueries({
      queryKey: queryKeys.messages.history(bookingId, { limit: HISTORY_LIMIT, offset: HISTORY_OFFSET }),
    });
  }, [queryClient, HISTORY_LIMIT, HISTORY_OFFSET]);

  return {
    threadMessages,
    messagesByThread,
    archivedMessagesByThread,
    trashMessagesByThread,
    loadThreadMessages,
    handleSSEMessage,
    handleSendMessage,
    handleArchiveConversation,
    handleDeleteConversation,
    setThreadMessagesForDisplay,
    updateThreadMessage,
    invalidateConversationCache,
  };
}
