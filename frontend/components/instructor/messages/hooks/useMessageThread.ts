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
  fetchMessageHistory,
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
import { mapMessageFromResponse, computeUnreadFromMessages, formatRelativeTime } from '../utils';

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
  const queryClient = useQueryClient();

  // Thread messages state
  const [threadMessages, setThreadMessages] = useState<MessageWithAttachments[]>([]);
  const [messagesByThread, setMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});
  const [archivedMessagesByThread, setArchivedMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});
  const [trashMessagesByThread, setTrashMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});


  // Refs for current state access in callbacks
  const messagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const archivedMessagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const trashMessagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const threadMessagesRef = useRef<MessageWithAttachments[]>([]);
  const markedReadThreadsRef = useRef<Map<string, number>>(new Map());
  const fetchingThreadsRef = useRef<Set<string>>(new Set());
  const loadedThreadsRef = useRef<Set<string>>(new Set());

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

    // Skip if already loaded or loading
    if (loadedThreadsRef.current.has(selectedChat)) return;
    if (fetchingThreadsRef.current.has(selectedChat)) return;

    fetchingThreadsRef.current.add(selectedChat);

    const bookingId = activeConversation.primaryBookingId;
    if (!bookingId) {
      fetchingThreadsRef.current.delete(selectedChat);
      return;
    }

    const fetchMessages = async () => {
      try {
        const history = await fetchMessageHistory(bookingId, { limit: 100, offset: 0 });
        const messages = history.messages || [];

        const mappedMessages = messages.map((msg) =>
          mapMessageFromResponse(msg, activeConversation, currentUserId)
        );

        // DON'T filter by message flags - archive/trash is conversation-level state
        // Just use all mapped messages for the conversation
        const allMessages = mappedMessages;

        // MERGE instead of REPLACE - keep SSE messages that arrived but aren't in history yet
        const existing = messagesByThreadRef.current[selectedChat] || [];
        const historyIds = new Set(allMessages.map(m => m.id));

        // Keep any messages that arrived via SSE but aren't in history yet
        const sseOnlyMessages = existing.filter(m => !historyIds.has(m.id));

        // Combine and sort by timestamp
        const mergedMessages = [...allMessages, ...sseOnlyMessages].sort(
          (a, b) => {
            const timeA = new Date(a.createdAt || '').getTime();
            const timeB = new Date(b.createdAt || '').getTime();
            return timeA - timeB;
          }
        );

        // Store in the main cache
        setMessagesByThread((prev) => ({ ...prev, [selectedChat]: mergedMessages }));

        // Display ALL messages regardless of view mode
        // The read-only state is handled by the UI based on conversation state, not message flags
        setThreadMessages(mergedMessages);

        // Update conversation unread count
        const unreadCount = computeUnreadFromMessages(messages, activeConversation, currentUserId);
        setConversations((prev) =>
          prev.map((conv) =>
            conv.id === selectedChat ? { ...conv, unread: unreadCount } : conv
          )
        );

        loadedThreadsRef.current.add(selectedChat);

        // Mark messages as read (continuously, not just once)
        if (unreadCount > 0) {
          // Only prevent duplicate calls for the SAME unread count
          const lastCount = markedReadThreadsRef.current.get(bookingId) ?? -1;
          if (lastCount !== unreadCount) {
            markedReadThreadsRef.current.set(bookingId, unreadCount);
            try {
              await markMessagesAsReadImperative({ booking_id: bookingId });
              setConversations((prev) =>
                prev.map((conv) =>
                  conv.id === selectedChat ? { ...conv, unread: 0 } : conv
                )
              );
              markedReadThreadsRef.current.set(bookingId, 0);
            } catch {
              markedReadThreadsRef.current.set(bookingId, lastCount);
            }
          }
        } else {
          // No unread messages, reset the counter
          markedReadThreadsRef.current.set(bookingId, 0);
        }
      } catch (error) {
        logger.error('Failed to fetch messages for conversation', { conversationId: selectedChat, error });
      } finally {
        fetchingThreadsRef.current.delete(selectedChat);
      }
    };

    void fetchMessages();
  }, [currentUserId, setConversations]);

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
        return updated;
      }
      // Only add new messages from other users
      if (isOwnMessage) return prev;
      return [...prev, mappedMessage];
    });

    // Update conversation preview
    setConversations((prev) =>
      prev.map((conv) => {
        if (conv.id !== selectedChat) return conv;
        return {
          ...conv,
          lastMessage: mappedMessage.text,
          timestamp: formatRelativeTime(mappedMessage.createdAt),
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
  }, [currentUserId, setConversations, queryClient]);

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
  }, [currentUserId, setConversations]);

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
    loadedThreadsRef.current.delete(conversationId);
  }, []);

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
