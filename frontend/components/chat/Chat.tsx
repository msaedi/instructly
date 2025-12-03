// frontend/components/chat/Chat.tsx
'use client';

/**
 * Mobile-first chat component for booking conversations.
 *
 * Features:
 * - Real-time messaging via SSE
 * - Auto-scroll to bottom on new messages
 * - Connection status indicator
 * - Mobile keyboard handling
 * - Message grouping by sender
 * - Date separators
 * - Loading and error states
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { format, isToday, isYesterday } from 'date-fns';
import { Send, Loader2, AlertCircle, WifiOff, Check, CheckCheck, ChevronDown, Pencil } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useMessageStream } from '@/providers/UserMessageStreamProvider';
import {
  useMessageConfig,
  useMessageHistory,
  useSendMessage,
  useMarkMessagesAsRead,
  useEditMessage,
  useAddReaction,
  useRemoveReaction,
  useSendTypingIndicator,
} from '@/src/api/services/messages';
import { queryKeys } from '@/src/api/queryKeys';
import type { MessageResponse } from '@/src/api/generated/instructly.schemas';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';

// Connection status enum (internal to Chat component)
enum ConnectionStatus {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  ERROR = 'error',
  RECONNECTING = 'reconnecting',
}

// Type for read_by entries from message response
type ReadByEntry = { user_id: string; read_at: string };

// Extended message type with reactions
interface MessageWithReactions extends MessageResponse {
  my_reactions?: string[];
  reactions?: Record<string, number>;
}

interface ChatProps {
  bookingId: string;
  currentUserId: string;
  currentUserName: string;
  otherUserName: string;
  className?: string;
  onClose?: () => void;
  isReadOnly?: boolean;
}

export function Chat({
  bookingId,
  currentUserId,
  currentUserName,
  otherUserName,
  className,
  onClose: _onClose,
  isReadOnly = false,
}: ChatProps) {
  // Config: fetched from backend via React Query (prevents duplicate API calls)
  const { data: messageConfig } = useMessageConfig();
  const editWindowMinutes = messageConfig?.edit_window_minutes ?? 5;

  const editingTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const MAX_EDIT_ROWS = 5;
  const EDIT_LINE_HEIGHT_PX = 20; // approx for text-[15px] leading-5
  const autosizeEditingTextarea = useCallback(() => {
    const el = editingTextareaRef.current;
    if (!el) return;
    el.style.height = '0px';
    const cap = MAX_EDIT_ROWS * EDIT_LINE_HEIGHT_PX;
    const newHeight = Math.min(el.scrollHeight, cap);
    el.style.height = `${newHeight}px`;
    el.style.overflowY = el.scrollHeight > cap ? 'auto' : 'hidden';
  }, []);

  // (moved autosize effect below where edit state is declared)
  const [inputMessage, setInputMessage] = useState('');
  const [isAtBottom, setIsAtBottom] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Fetch message history
  const {
    data: historyData,
    isLoading: isLoadingHistory,
    error: historyError,
  } = useMessageHistory(bookingId);


  // Mutations - destructure mutate functions for stable references
  const queryClient = useQueryClient();
  const sendMessageMutation = useSendMessage();
  const { mutate: markMessagesAsReadMutate } = useMarkMessagesAsRead();
  const editMessageMutation = useEditMessage();
  const addReactionMutation = useAddReaction();
  const removeReactionMutation = useRemoveReaction();
  const sendTypingMutation = useSendTypingIndicator();
  const lastMarkedUnreadByBookingRef = useRef<Record<string, string | null>>({});

  // Real-time messages via SSE (Phase 4: per-user inbox)
  const { subscribe, isConnected, connectionError } = useMessageStream();
  const [realtimeMessages, setRealtimeMessages] = useState<MessageResponse[]>([]);
  const [readReceipts, setReadReceipts] = useState<
    Record<string, Array<{ user_id: string; read_at: string }>>
  >({});
  const [typingStatus, setTypingStatus] = useState<{
    userId: string;
    userName: string;
    until: number;
  } | null>(null);
  const [reactionDeltas, setReactionDeltas] = useState<
    Record<string, Record<string, number>>
  >({});
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Map connection state to legacy status enum
  const connectionStatus: ConnectionStatus = connectionError
    ? ConnectionStatus.ERROR
    : isConnected
    ? ConnectionStatus.CONNECTED
    : ConnectionStatus.DISCONNECTED;

  const reconnect = () => {
    // Reconnect is automatic in new implementation
    window.location.reload();
  };

  // Extract SSE handlers to useCallback for stable references (fixes re-render loop)
  const handleSSEMessage = useCallback((message: { id: string; content: string; sender_id: string; sender_name: string; created_at: string; booking_id: string; delivered_at?: string | null }, isMine: boolean) => {
    logger.debug('[MSG-DEBUG] Chat: handleSSEMessage CALLED', {
      messageId: message?.id,
      content: message?.content?.substring(0, 50),
      isMine,
      bookingId,
      timestamp: new Date().toISOString(),
    });

    // Add message to realtime state, or update existing message with new fields (e.g., delivered_at)
    setRealtimeMessages((prev) => {
      logger.debug('[MSG-DEBUG] Chat: setRealtimeMessages called', {
        prevLength: prev.length,
        messageId: message.id,
        timestamp: new Date().toISOString(),
      });
      const existingIndex = prev.findIndex((m) => m.id === message.id);
      if (existingIndex !== -1) {
        // Update existing message (e.g., to add delivered_at timestamp)
        logger.debug('[MSG-DEBUG] Chat: Updating existing message', {
          messageId: message.id,
          existingIndex,
        });
        const updated = [...prev];
        const deliveredAt = message.delivered_at ?? updated[existingIndex]!.delivered_at;
        updated[existingIndex] = {
          ...updated[existingIndex]!,
          ...(deliveredAt ? { delivered_at: deliveredAt } : {}),
        };
        return updated;
      }
      logger.debug('[MSG-DEBUG] Chat: Adding NEW message to realtimeMessages', {
        messageId: message.id,
        content: message.content?.substring(0, 30),
        newLength: prev.length + 1,
        timestamp: new Date().toISOString(),
      });
      return [
        ...prev,
        {
          id: message.id,
          content: message.content,
          sender_id: message.sender_id,
          booking_id: message.booking_id,
          created_at: message.created_at,
          updated_at: message.created_at,
          is_deleted: false,
          ...(message.delivered_at ? { delivered_at: message.delivered_at } : {}),
        } as MessageResponse,
      ];
    });

    // Mark message as read if it's from the other user
    if (!isMine && message.sender_id !== currentUserId) {
      markMessagesAsReadMutate({ data: { message_ids: [message.id] } });
    }
  }, [bookingId, currentUserId, markMessagesAsReadMutate]);

  const handleSSETyping = useCallback((userId: string, userName: string, isTyping: boolean) => {
    if (isTyping) {
      setTypingStatus({ userId, userName, until: Date.now() + 3000 });
      // Clear typing after 3 seconds if no update
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = setTimeout(() => setTypingStatus(null), 3000);
    } else {
      setTypingStatus(null);
    }
  }, []);

  const handleReadReceipt = useCallback((messageIds: string[], readerId: string) => {
    // Defensive check: SSE event might send undefined
    if (!messageIds || !Array.isArray(messageIds)) {
      logger.warn('[Chat] Invalid read receipt event', { messageIds, readerId });
      return;
    }

    setReadReceipts((prev) => {
      const updated = { ...prev };
      messageIds.forEach((msgId) => {
        const existing = updated[msgId] || [];
        if (!existing.find((r) => r.user_id === readerId)) {
          updated[msgId] = [
            ...existing,
            { user_id: readerId, read_at: new Date().toISOString() },
          ];
        }
      });
      return updated;
    });
  }, []);

  const handleReaction = useCallback((messageId: string, emoji: string, action: 'added' | 'removed', userId: string) => {
    // Skip SSE deltas for current user's own reactions - already handled optimistically
    if (userId === currentUserId) {
      return;
    }

    setReactionDeltas((prev) => {
      const current = prev[messageId] || {};
      const delta = action === 'added' ? 1 : -1;
      const nextCount = (current[emoji] || 0) + delta;
      const updated = {
        ...prev,
        [messageId]: { ...current, [emoji]: nextCount },
      };
      return updated;
    });
  }, [currentUserId]);

  const handleMessageEdited = useCallback((messageId: string, newContent: string, _editorId: string) => {
    logger.debug('[MSG-DEBUG] handleMessageEdited CALLED', {
      messageId,
      newContent,
      currentBookingId: bookingId,
    });

    // Update local realtime messages state (for messages sent this session)
    setRealtimeMessages((prev) => {
      const messageIndex = prev.findIndex((m) => m.id === messageId);
      if (messageIndex !== -1) {
        logger.debug('[MSG-DEBUG] handleMessageEdited updating realtimeMessages');
        const updated = [...prev];
        updated[messageIndex] = {
          ...updated[messageIndex]!,
          content: newContent,
          edited_at: new Date().toISOString(),
        };
        return updated;
      }
      return prev;
    });

    // Invalidate React Query cache to refetch (for historical messages)
    // This ensures the edit is reflected even if message was from history
    void queryClient.invalidateQueries({
      queryKey: queryKeys.messages.history(bookingId),
      exact: false,
    });

    logger.debug('[MSG-DEBUG] handleMessageEdited DONE - updated local state + invalidated cache');
  }, [bookingId, queryClient]);

  // Subscribe to this conversation's events
  useEffect(() => {
    logger.debug('[MSG-DEBUG] Chat: subscription useEffect running', {
      bookingId,
      hasSubscribe: !!subscribe,
      hasHandleSSEMessage: !!handleSSEMessage,
      timestamp: new Date().toISOString(),
    });

    if (!bookingId) {
      logger.debug('[MSG-DEBUG] Chat: subscription useEffect - no bookingId, returning');
      return;
    }

    // Invalidate message history cache when chat opens to fetch any missed messages
    // This ensures messages sent while chat was closed are loaded
    void queryClient.invalidateQueries({
      queryKey: queryKeys.messages.history(bookingId),
      exact: false,
    });

    logger.debug('[MSG-DEBUG] Chat: Subscribing to conversation', {
      bookingId,
      timestamp: new Date().toISOString(),
    });

    const unsubscribe = subscribe(bookingId, {
      onMessage: handleSSEMessage,
      onTyping: handleSSETyping,
      onReadReceipt: handleReadReceipt,
      onReaction: handleReaction,
      onMessageEdited: handleMessageEdited,
    });

    logger.debug('[MSG-DEBUG] Chat: Subscription complete', {
      bookingId,
      timestamp: new Date().toISOString(),
    });

    return () => {
      logger.debug('[MSG-DEBUG] Chat: Unsubscribing from conversation', {
        bookingId,
        timestamp: new Date().toISOString(),
      });
      unsubscribe();
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
  }, [bookingId, subscribe, handleSSEMessage, handleSSETyping, handleReadReceipt, handleReaction, handleMessageEdited, queryClient]);

  // Combine history and real-time messages with deduplication
  const allMessages = React.useMemo(() => {
    logger.debug('[MSG-DEBUG] Chat: allMessages memo recalculating', {
      historyCount: historyData?.messages?.length ?? 0,
      realtimeCount: realtimeMessages.length,
      realtimeIds: realtimeMessages.map(m => m.id),
      timestamp: new Date().toISOString(),
    });

    const messageMap = new Map<string, MessageResponse>();

    // Add history messages
    (historyData?.messages || []).forEach(msg => {
      messageMap.set(msg.id, msg);
    });

    // Add real-time messages (only if not already in history)
    // SSE now echoes messages to sender with is_mine flag
    realtimeMessages.forEach(msg => {
      if (!messageMap.has(msg.id)) {
        messageMap.set(msg.id, msg);
        logger.debug('[MSG-DEBUG] Chat: allMessages - added realtime message', {
          messageId: msg.id,
          content: msg.content?.substring(0, 30),
        });
      } else {
        logger.debug('[MSG-DEBUG] Chat: allMessages - skipped duplicate', {
          messageId: msg.id,
        });
      }
    });

    const result = Array.from(messageMap.values()).sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );

    logger.debug('[MSG-DEBUG] Chat: allMessages result', {
      totalCount: result.length,
      lastMessageId: result[result.length - 1]?.id,
      lastMessageContent: result[result.length - 1]?.content?.substring(0, 30),
    });

    return result;
  }, [historyData?.messages, realtimeMessages]);

  // Build a stable read map derived from server-provided read_by and live receipts
  const mergedReadReceipts = React.useMemo(() => {
    const map: Record<string, Array<{ user_id: string; read_at: string }>> = { ...readReceipts };
    for (const m of allMessages) {
      if (m.read_by && Array.isArray(m.read_by)) {
        const existing = map[m.id] || [];
        const combined = [...existing];
        const readByEntries = m.read_by as ReadByEntry[];
        for (const r of readByEntries) {
          if (!combined.find(x => x.user_id === r.user_id && x.read_at === r.read_at)) {
            if (r.user_id && r.read_at) combined.push({ user_id: r.user_id, read_at: r.read_at });
          }
        }
        map[m.id] = combined;
      }
    }
    return map;
  }, [allMessages, readReceipts]);

  const latestUnreadMessageId = React.useMemo(() => {
    let latest: { id: string; ts: number } | null = null;

    for (const message of allMessages) {
      if (message.sender_id === currentUserId) continue;

      const receipts = mergedReadReceipts[message.id] || [];
      const wasRead = receipts.some(receipt => receipt.user_id === currentUserId && !!receipt.read_at);
      if (wasRead) continue;

      const createdAt = new Date(message.created_at).getTime();
      if (Number.isNaN(createdAt)) continue;

      if (!latest || createdAt > latest.ts) {
        latest = { id: message.id, ts: createdAt };
      }
    }

    return latest?.id ?? null;
  }, [allMessages, mergedReadReceipts, currentUserId]);

  // Determine the latest own message that has a read receipt (global, not per-day group)
  const lastOwnReadMessageId = React.useMemo(() => {
    let latest: { id: string; ts: number } | null = null;
    for (const m of allMessages) {
      if (m.sender_id !== currentUserId) continue;
      const reads = mergedReadReceipts[m.id] || [];
      if (reads.length === 0) continue;
      const t = new Date(m.created_at).getTime();
      if (!latest || t > latest.ts) latest = { id: m.id, ts: t };
    }
    return latest?.id ?? null;
  }, [allMessages, mergedReadReceipts, currentUserId]);

  // Auto-scroll to bottom
  const scrollToBottom = useCallback((smooth = true) => {
    messagesEndRef.current?.scrollIntoView({
      behavior: smooth ? 'smooth' : 'auto',
    });
  }, []);

  // Check if user is at bottom of scroll
  const handleScroll = useCallback(() => {
    if (!scrollContainerRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const threshold = 100;
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < threshold);
  }, []);

  // Scroll to bottom on new messages (if already at bottom)
  useEffect(() => {
    if (isAtBottom && allMessages.length > 0) {
      scrollToBottom();
    }
  }, [allMessages.length, isAtBottom, scrollToBottom]);

  // Mark unread messages exactly once per newest unread message per booking
  useEffect(() => {
    if (!bookingId) {
      return;
    }

    if (!latestUnreadMessageId) {
      delete lastMarkedUnreadByBookingRef.current[bookingId];
      return;
    }

    const lastMarked = lastMarkedUnreadByBookingRef.current[bookingId];
    if (lastMarked === latestUnreadMessageId) {
      return;
    }

    lastMarkedUnreadByBookingRef.current[bookingId] = latestUnreadMessageId;
    markMessagesAsReadMutate({ data: { booking_id: bookingId } });
  }, [bookingId, latestUnreadMessageId, markMessagesAsReadMutate]);

  // Handle send message - SSE echoes message back with is_mine flag
  const handleSendMessage = async () => {
    const content = inputMessage.trim();
    if (!content) return;

    logger.debug('[MSG-DEBUG] Message SEND: Starting', {
      bookingId,
      contentLength: content.length,
      timestamp: new Date().toISOString()
    });

    // Clear input immediately for responsiveness
    setInputMessage('');

    // Cancel any pending typing indicator
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = null;
    }

    try {
      logger.debug('[MSG-DEBUG] Message SEND: Calling mutation', {
        bookingId,
        timestamp: new Date().toISOString()
      });
      const result = await sendMessageMutation.mutateAsync({
        data: {
          booking_id: bookingId,
          content,
        },
      });
      logger.debug('[MSG-DEBUG] Message SEND: Success', {
        messageId: result?.message?.id,
        success: result?.success,
        timestamp: new Date().toISOString()
      });

      // Use server response to set delivered_at immediately for own messages
      const serverMessage = result?.message;
      if (serverMessage) {
        setRealtimeMessages((prev) => {
          const existingIndex = prev.findIndex((m) => m.id === serverMessage.id);
          if (existingIndex !== -1) {
            const updated = [...prev];
            updated[existingIndex] = {
              ...updated[existingIndex]!,
              delivered_at:
                serverMessage.delivered_at ??
                updated[existingIndex]!.delivered_at ??
                null,
            };
            return updated;
          }

          return [
            ...prev,
            {
              id: serverMessage.id,
              content: serverMessage.content,
              sender_id: serverMessage.sender_id,
              booking_id: serverMessage.booking_id,
              created_at: serverMessage.created_at,
              updated_at: serverMessage.updated_at ?? serverMessage.created_at,
              is_deleted: serverMessage.is_deleted ?? false,
              delivered_at: serverMessage.delivered_at ?? null,
            } as MessageResponse,
          ];
        });
      }

      // SSE echo will still arrive; dedup handled in allMessages
      scrollToBottom();
    } catch (error) {
      logger.error('[MSG-DEBUG] Message SEND: FAILED', {
        error: error instanceof Error ? error.message : error,
        bookingId,
        timestamp: new Date().toISOString()
      });
      // Restore input message on error so user can retry
      setInputMessage(content);
    }
  };

  // Handle enter key (send on Enter, new line on Shift+Enter)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSendMessage();
    }
  };

  // Typing indicator: send best-effort signal with debounce (1s)
  const handleTyping = () => {
    try {
      sendTypingMutation.mutate({ bookingId });
    } catch {}
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputMessage(e.target.value);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => {
      void handleTyping();
    }, 300); // 300ms debounce for more responsive typing indicator
  };

  // Quick reactions toggle per-message
  const [openReactionsForMessageId, setOpenReactionsForMessageId] = useState<string | null>(null);
  const [processingReaction, setProcessingReaction] = useState<string | null>(null);
  const quickEmojis = ['👍', '❤️', '😊', '😮', '🎉'];
  const handleAddReaction = async (messageId: string, emoji: string) => {
    logger.debug('[MSG-DEBUG] Reaction: Starting', {
      messageId,
      emoji,
      bookingId,
      timestamp: new Date().toISOString()
    });

    // For optimistic/temporary messages with negative IDs
    if (messageId.startsWith('-')) {
      logger.debug('[MSG-DEBUG] Reaction: Skipping temp message');
      return;
    }

    // Prevent multiple simultaneous reactions GLOBALLY (not just per message)
    if (processingReaction !== null) {
      logger.warn('[MSG-DEBUG] Reaction: Already processing, ignoring', {
        processingReaction,
        newRequest: { messageId, emoji }
      });
      return;
    }

    try {
      setProcessingReaction(messageId);

      // Optimistic UX: close popover immediately
      setOpenReactionsForMessageId(null);

      // Find the message to check current user's reaction
      const message = allMessages.find(m => m.id === messageId);
      if (!message) {
        logger.error('[MSG-DEBUG] Reaction: Message not found', { messageId });
        return;
      }

      // Get current state
      const myReactions = (message as MessageWithReactions)?.my_reactions || [];
      const localReaction = userReactions[messageId];
      const currentReaction = localReaction !== undefined ? localReaction : myReactions[0];

      logger.debug('[MSG-DEBUG] Reaction: Current state', {
        messageId,
        requestedEmoji: emoji,
        serverReactions: myReactions,
        localReaction,
        currentReaction,
        timestamp: new Date().toISOString()
      });

      // If user is trying to add a reaction when they already have one (and it's different)
      // Force remove the old one first
      if (currentReaction && currentReaction !== emoji) {
        logger.debug('[MSG-DEBUG] Reaction: Replacing existing', {
          oldEmoji: currentReaction,
          newEmoji: emoji,
          messageId,
          timestamp: new Date().toISOString()
        });
        // Update local state immediately to show the change
        setUserReactions(prev => ({ ...prev, [messageId]: emoji }));

        // Remove old reaction
        try {
          logger.debug('[MSG-DEBUG] Reaction: Calling removeReactionMutation', {
            messageId,
            emoji: currentReaction,
            timestamp: new Date().toISOString()
          });
          await removeReactionMutation.mutateAsync({ messageId, data: { emoji: currentReaction } });
          logger.debug('[MSG-DEBUG] Reaction: removeReactionMutation SUCCESS', { timestamp: new Date().toISOString() });
        } catch (err) {
          logger.error('[MSG-DEBUG] Reaction: removeReactionMutation FAILED', {
            error: err instanceof Error ? err.message : err,
            messageId,
            emoji: currentReaction,
            timestamp: new Date().toISOString()
          });
          // Revert local state
          setUserReactions(prev => ({ ...prev, [messageId]: currentReaction }));
          return;
        }

        // Add new reaction
        try {
          logger.debug('[MSG-DEBUG] Reaction: Calling addReactionMutation', {
            messageId,
            emoji,
            timestamp: new Date().toISOString()
          });
          await addReactionMutation.mutateAsync({ messageId, data: { emoji } });
          logger.debug('[MSG-DEBUG] Reaction: addReactionMutation SUCCESS', { timestamp: new Date().toISOString() });
        } catch (err) {
          logger.error('[MSG-DEBUG] Reaction: addReactionMutation FAILED', {
            error: err instanceof Error ? err.message : err,
            messageId,
            emoji,
            timestamp: new Date().toISOString()
          });
          // Revert to no reaction since we removed the old one
          setUserReactions(prev => ({ ...prev, [messageId]: null }));
          return;
        }
      } else if (currentReaction === emoji) {
        // Toggle off - remove the reaction
        logger.debug('[MSG-DEBUG] Reaction: Toggling off', {
          emoji,
          messageId,
          timestamp: new Date().toISOString()
        });
        setUserReactions(prev => ({ ...prev, [messageId]: null }));

        try {
          logger.debug('[MSG-DEBUG] Reaction: Calling removeReactionMutation for toggle', {
            messageId,
            emoji,
            timestamp: new Date().toISOString()
          });
          await removeReactionMutation.mutateAsync({ messageId, data: { emoji } });
          logger.debug('[MSG-DEBUG] Reaction: removeReactionMutation SUCCESS (toggle)', { timestamp: new Date().toISOString() });
        } catch (err) {
          logger.error('[MSG-DEBUG] Reaction: removeReactionMutation FAILED (toggle)', {
            error: err instanceof Error ? err.message : err,
            messageId,
            emoji,
            timestamp: new Date().toISOString()
          });
          // Revert local state
          setUserReactions(prev => ({ ...prev, [messageId]: emoji }));
        }
      } else {
        // No current reaction, add the new one
        logger.debug('[MSG-DEBUG] Reaction: Adding new', {
          emoji,
          messageId,
          timestamp: new Date().toISOString()
        });
        setUserReactions(prev => ({ ...prev, [messageId]: emoji }));

        try {
          logger.debug('[MSG-DEBUG] Reaction: Calling addReactionMutation (new)', {
            messageId,
            emoji,
            timestamp: new Date().toISOString()
          });
          await addReactionMutation.mutateAsync({ messageId, data: { emoji } });
          logger.debug('[MSG-DEBUG] Reaction: addReactionMutation SUCCESS (new)', { timestamp: new Date().toISOString() });
        } catch (err) {
          logger.error('[MSG-DEBUG] Reaction: addReactionMutation FAILED (new)', {
            error: err instanceof Error ? err.message : err,
            messageId,
            emoji,
            timestamp: new Date().toISOString()
          });
          // Revert local state
          setUserReactions(prev => ({ ...prev, [messageId]: null }));
        }
      }

      // Extra safety: if server still has multiple reactions, clean them up
      const updatedMessage = allMessages.find(m => m.id === messageId);
      const updatedReactions = (updatedMessage as MessageWithReactions)?.my_reactions || [];
      if (updatedReactions.length > 1) {
        logger.warn(`Message still has ${updatedReactions.length} reactions after update, cleaning up extras`);
        const keepEmoji = userReactions[messageId] || updatedReactions[0];
        for (const extraEmoji of updatedReactions) {
          if (extraEmoji !== keepEmoji) {
            await removeReactionMutation.mutateAsync({ messageId, data: { emoji: extraEmoji } });
          }
        }
      }

    } catch (error) {
      logger.error('Failed to handle reaction', error);
      // Revert optimistic update on error
      const message = allMessages.find(m => m.id === messageId);
      if (message) {
        const myReactions = (message as MessageWithReactions)?.my_reactions || [];
        const serverReaction = myReactions[0];
        setUserReactions(prev => ({
          ...prev,
          [messageId]: serverReaction || null
        }));
      }
    } finally {
      // Invalidate message history cache so reactions persist on reopen
      // This ensures fresh data is fetched next time chat is opened
      void queryClient.invalidateQueries({
        queryKey: queryKeys.messages.history(bookingId),
        exact: false,
      });
      // Add a small delay before allowing new reactions to prevent race conditions
      setTimeout(() => {
        setProcessingReaction(null);
      }, 200);
    }
  };

  // Edit mode state
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState<string>("");
  const [isSavingEdit, setIsSavingEdit] = useState<boolean>(false);
  useEffect(() => {
    if (editingMessageId) {
      requestAnimationFrame(() => autosizeEditingTextarea());
    }
  }, [editingMessageId, editingContent, autosizeEditingTextarea]);
  const startEdit = (message: MessageResponse) => {
    if (!canEditMessage(message)) return;
    setEditingMessageId(message.id);
    setEditingContent(message.content);
  };
  const cancelEdit = () => {
    setEditingMessageId(null);
    setEditingContent("");
  };
  const saveEdit = async () => {
    if (!editingMessageId || !editingContent.trim()) return;
    const target = allMessages.find(m => m.id === editingMessageId);
    if (!target || !canEditMessage(target)) return;
    setIsSavingEdit(true);
    try {
      await editMessageMutation.mutateAsync({
        messageId: editingMessageId,
        data: { content: editingContent.trim() },
      });
      setEditingMessageId(null);
      setEditingContent("");
    } finally {
      setIsSavingEdit(false);
    }
  };

  const canEditMessage = (message: MessageResponse): boolean => {
    if (message.sender_id !== currentUserId) return false;
    const created = new Date(message.created_at).getTime();
    const now = Date.now();
    const diffMinutes = (now - created) / 60000;
    return diffMinutes <= editWindowMinutes;
  };

  // Track SINGLE reaction per message (messageId -> emoji or null)
  // This is the source of truth for user's reactions
  const [userReactions, setUserReactions] = useState<Record<string, string | null>>({});

  // Apply reaction deltas from SSE to track real-time updates
  useEffect(() => {
    // Process reaction deltas to determine current user reactions
    Object.entries(reactionDeltas).forEach(([_messageId, _reactions]) => {
      // Find which reactions belong to current user based on delta changes
      // This is a workaround since SSE doesn't tell us WHO added/removed reactions
      // We'll rely on our local state as source of truth
    });
  }, [reactionDeltas]);

  // Initialize userReactions from server data when messages load
  // Also clean up any multiple reactions (enforce single emoji)
  useEffect(() => {
    const newReactions: Record<string, string | null> = {};
    const cleanupMessages: Array<{messageId: string, keepEmoji: string, removeEmojis: string[]}> = [];

    allMessages.forEach(message => {
      // Only set if we don't already have a local state for this message
      if (userReactions[message.id] === undefined) {
        const myReactions = (message as MessageWithReactions).my_reactions || [];
        // Only track the FIRST reaction (enforce single emoji)
        newReactions[message.id] = myReactions[0] || null;

        // If server has multiple reactions, schedule cleanup
        if (myReactions.length > 1) {
          logger.warn(`Message ${message.id} has ${myReactions.length} reactions, cleaning up to keep only: ${myReactions[0]}`);
          cleanupMessages.push({
            messageId: message.id,
            keepEmoji: myReactions[0] || '',
            removeEmojis: myReactions.slice(1)
          });
        }
      }
    });

    // Only update if there are new reactions to add
    if (Object.keys(newReactions).length > 0) {
      setUserReactions(prev => ({
        ...newReactions,
        ...prev // Preserve any existing local state
      }));
    }

    // Clean up multiple reactions on server
    if (cleanupMessages.length > 0) {
      (async () => {
        for (const cleanup of cleanupMessages) {
          for (const emojiToRemove of cleanup.removeEmojis) {
            try {
              await removeReactionMutation.mutateAsync({
                messageId: cleanup.messageId,
                data: { emoji: emojiToRemove },
              });
              logger.info(`Cleaned up extra reaction ${emojiToRemove} from message ${cleanup.messageId}`);
            } catch (error) {
              logger.error(`Failed to clean up reaction ${emojiToRemove}`, error);
            }
          }
        }
      })();
    }
  }, [allMessages, userReactions, removeReactionMutation]); // Only re-run when messages or reactions change

  // Local reaction toggle function removed - optimistic updates handled in handleAddReaction

  const isEmojiMyReacted = (message: MessageResponse, emoji: string): boolean => {
    // Check our local state for the current reaction
    const localReaction = userReactions[message.id];
    if (localReaction !== undefined) {
      // If local state is set, use it (even if null)
      return localReaction === emoji;
    }

    // Fall back to server state - only consider FIRST reaction
    const myReactions = (message as MessageWithReactions).my_reactions || [];
    return myReactions.length > 0 && myReactions[0] === emoji;
  };

  // Format message date
  const formatMessageDate = (date: string) => {
    const messageDate = new Date(date);

    if (isToday(messageDate)) {
      return format(messageDate, 'h:mm a');
    } else if (isYesterday(messageDate)) {
      return `Yesterday ${format(messageDate, 'h:mm a')}`;
    } else {
      return format(messageDate, 'MMM d, h:mm a');
    }
  };

  // Get date separator text
  const getDateSeparator = (date: string) => {
    const messageDate = new Date(date);

    if (isToday(messageDate)) {
      return 'Today';
    } else if (isYesterday(messageDate)) {
      return 'Yesterday';
    } else {
      return format(messageDate, 'EEEE, MMMM d');
    }
  };

  // Group messages by date
  const messagesByDate = allMessages.reduce((groups, message) => {
    const date = new Date(message.created_at).toDateString();
    if (!groups[date]) {
      groups[date] = [];
    }
    groups[date].push(message);
    return groups;
  }, {} as Record<string, MessageResponse[]>);

  // Connection status component
  const ConnectionIndicator = () => {
    if (connectionStatus === ConnectionStatus.CONNECTED) {
      return null;
    }

    return (
      <div className={cn(
        'flex items-center justify-center py-2 px-4 text-sm',
        connectionStatus === ConnectionStatus.ERROR && 'bg-red-50 text-red-700',
        connectionStatus === ConnectionStatus.DISCONNECTED && 'bg-gray-50 text-gray-700'
      )}>
        {connectionStatus === ConnectionStatus.ERROR && (
          <>
            <AlertCircle className="w-4 h-4 mr-2" />
            Connection error
            <button
              onClick={reconnect}
              className="ml-2 underline hover:no-underline"
            >
              Retry
            </button>
          </>
        )}
        {connectionStatus === ConnectionStatus.DISCONNECTED && (
          <>
            <WifiOff className="w-4 h-4 mr-2" />
            Disconnected
            <button
              onClick={reconnect}
              className="ml-2 underline hover:no-underline"
            >
              Connect
            </button>
          </>
        )}
      </div>
    );
  };

  // Optional typing indicator bar (ephemeral)
  // We will show this via SSE hook in phase 2 UI update (placeholder)

  // Loading state
  if (isLoadingHistory) {
    return (
      <div className={cn('flex items-center justify-center h-full bg-gradient-to-b from-gray-50 to-white', className)}>
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  // Error state
  if (historyError) {
    return (
      <div className={cn('flex flex-col items-center justify-center h-full p-4', className)}>
        <AlertCircle className="w-12 h-12 text-red-500 mb-2" />
        <p className="text-red-600 text-center">Failed to load messages</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-2 text-blue-600 underline hover:no-underline"
        >
          Reload
        </button>
      </div>
    );
  }

  return (
    <div className={cn('relative flex flex-col h-full min-h-0 bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-900', className)}>
      {/* Connection status */}
      <div className="sticky top-0 z-10">
        <ConnectionIndicator />
      </div>

      {/* Messages container */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto px-3 sm:px-4 py-3 sm:py-4 space-y-3 sm:space-y-4"
      >
        {allMessages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
            <p>No messages yet. Start the conversation!</p>
          </div>
        ) : (
          <>
            {Object.entries(messagesByDate).map(([date, messages]) => (
              <div key={date}>
                {/* Date separator */}
                <div className="relative my-6">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-gray-200 dark:border-gray-800" />
                  </div>
                  <div className="relative flex justify-center">
                    <span className="bg-white px-3 py-1 text-xs text-gray-600 rounded-full shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-800">
                      {getDateSeparator(messages[0]?.created_at || '')}
                    </span>
                  </div>
                </div>

                {/* Messages for this date */}
                {messages.map((message, index) => {
                  const isOwn = message.sender_id === currentUserId;
                  const showSender = index === 0 ||
                    messages[index - 1]?.sender_id !== message.sender_id;

                  return (
                    <div
                      key={message.id}
                      className={cn(
                        'flex',
                        isOwn ? 'justify-end' : 'justify-start',
                        !showSender && 'mt-1.5'
                      )}
                    >
                      <div
                        className={cn(
                          'max-w-[82%] xs:max-w-[78%] sm:max-w-[60%]',
                          isOwn ? 'items-end' : 'items-start'
                        )}
                      >
                        {/* Sender name */}
                        {showSender && (
                          <div className={cn(
                            'text-xs text-gray-500 dark:text-gray-400 mb-1',
                            isOwn ? 'text-right mr-2' : 'ml-2'
                          )}>
                            {isOwn ? currentUserName : otherUserName}
                          </div>
                        )}

                        {/* Message bubble */}
                         <div
                          className={cn(
                            'rounded-2xl px-3.5 py-2 break-words shadow-sm select-text text-[15px] leading-5 sm:text-sm',
                            isOwn
                              ? 'bg-gradient-to-tr from-purple-700 to-purple-600 text-white ring-1 ring-[#7E22CE]/10'
                              : 'bg-white text-gray-900 ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:ring-gray-700'
                          )}
                        >
                          {editingMessageId === message.id ? (
                            <div className={cn('flex items-end gap-2', isOwn ? 'text-white' : 'text-gray-900')}>
                              <div className={cn('flex-1 rounded-md', isOwn ? 'bg-purple-500/15' : 'bg-gray-100')}>
                                <textarea
                                  ref={editingTextareaRef}
                                  value={editingContent}
                                  onChange={(e) => setEditingContent(e.target.value)}
                                  onInput={autosizeEditingTextarea}
                                  rows={1}
                                  className={cn('w-full resize-none rounded-md px-2 py-1 text-[15px] leading-5 outline-none focus:ring-[#7E22CE] focus:border-purple-500', isOwn ? 'bg-transparent text-white placeholder:text-blue-100' : 'bg-transparent text-gray-900 placeholder:text-gray-400')}
                                  style={{ overflowY: 'hidden', height: 'auto' }}
                                />
                              </div>
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={saveEdit}
                                  disabled={isSavingEdit || !editingContent.trim()}
                                  className={cn('text-xs rounded-md px-2 py-1 ring-1', isOwn ? 'bg-white/10 ring-white/20' : 'bg-gray-200 ring-gray-300')}
                                >
                                  {isSavingEdit ? 'Saving…' : 'Save'}
                                </button>
                                <button
                                  onClick={cancelEdit}
                                  className={cn('text-xs rounded-md px-2 py-1 ring-1', isOwn ? 'bg-white/10 ring-white/20' : 'bg-gray-200 ring-gray-300')}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p className="whitespace-pre-wrap">{message.content}</p>
                          )}
                          <div className={cn(
                            'flex items-center justify-end mt-1 space-x-1',
                            isOwn ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400'
                          )}>
                            <span className="text-xs">
                              {formatMessageDate(message.created_at)}
                            </span>
                            {isOwn && (
                              // WhatsApp-style indicators: gray sent → gray delivered → blue read
                              (mergedReadReceipts[message.id]?.length ?? 0) > 0 ? (
                                <CheckCheck className="w-3 h-3 text-blue-500" />
                              ) : message.delivered_at ? (
                                <CheckCheck className="w-3 h-3 text-gray-400" />
                              ) : (
                                <Check className="w-3 h-3 text-gray-400" />
                              )
                            )}
                            {message.edited_at && (
                              <span className={cn('text-[10px] ml-1', isOwn ? 'text-blue-100/80' : 'text-gray-400')}>edited</span>
                            )}
                            {isOwn && editingMessageId !== message.id && canEditMessage(message) && (
                              <button
                                onClick={() => startEdit(message)}
                                className={cn('ml-2 rounded-full p-1', isOwn ? 'hover:bg-white/10' : 'hover:bg-gray-100')}
                                aria-label="Edit message"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Reaction bar (counts) */}
                        {(() => {
                          const reactions = (message as MessageWithReactions).reactions || {};

                          // Build the display considering user's single reaction
                          const displayReactions: Record<string, number> = { ...reactions };

                          // Get user's current reaction (only one allowed)
                          const localReaction = userReactions[message.id];
                          const serverReaction = (message as MessageWithReactions).my_reactions?.[0];

                          // Adjust counts based on local state changes
                          if (localReaction !== undefined && localReaction !== serverReaction) {
                            // User changed their reaction locally
                            if (serverReaction) {
                              // Decrement old reaction
                              displayReactions[serverReaction] = Math.max(0, (displayReactions[serverReaction] || 0) - 1);
                              if (displayReactions[serverReaction] === 0) {
                                delete displayReactions[serverReaction];
                              }
                            }
                            if (localReaction) {
                              // Increment new reaction
                              displayReactions[localReaction] = (displayReactions[localReaction] || 0) + 1;
                            }
                          }

                          // Apply SSE reaction deltas for real-time updates from other users
                          const messageDelta = reactionDeltas[message.id];
                          if (messageDelta) {
                            Object.entries(messageDelta).forEach(([emoji, delta]) => {
                              displayReactions[emoji] = Math.max(0, (displayReactions[emoji] || 0) + delta);
                              if (displayReactions[emoji] === 0) {
                                delete displayReactions[emoji];
                              }
                            });
                          }

                          const entries = Object.entries(displayReactions).filter(([, c]) => c > 0);
                          if (entries.length === 0) return null;
                          return (
                          <div className={cn('mt-1 flex justify-end gap-1', isOwn ? 'pr-1' : 'pl-1')}>
                            {entries.map(([emoji, count]) => {
                              const mine = isEmojiMyReacted(message, emoji);
                              const isOwnMessage = message.sender_id === currentUserId;
                              return (
                                <button
                                  type="button"
                                  key={emoji}
                                  onClick={async () => {
                                    // Don't allow reactions on own messages
                                    if (isOwnMessage) return;
                                    // Prevent multiple simultaneous reactions
                                    if (processingReaction !== null) return;
                                    await handleAddReaction(message.id, emoji);
                                  }}
                                  disabled={isOwnMessage || processingReaction !== null}
                                  className={cn(
                                    'rounded-full px-2 py-0.5 text-xs ring-1 transition',
                                    mine ? 'bg-[#7E22CE] text-white ring-[#7E22CE]' : (isOwn ? 'bg-purple-50 text-[#7E22CE] ring-purple-200' : 'bg-gray-50 text-gray-700 ring-gray-200'),
                                    (isOwnMessage || processingReaction !== null) && 'cursor-default'
                                  )}
                                >
                                  {emoji} {count}
                                </button>
                              );
                            })}
                          </div>
                          );
                        })()}

                        {/* Add reaction control per message (other user's messages only) */}
                        {!isOwn && (
                          <div className={cn('mt-1 flex justify-end', isOwn ? 'pr-1' : 'pl-1')}>
                            <button
                              type="button"
                              onClick={() => setOpenReactionsForMessageId(openReactionsForMessageId === message.id ? null : message.id)}
                              disabled={processingReaction !== null}
                              className={cn(
                                'rounded-full px-2 py-0.5 text-xs ring-1 transition',
                                processingReaction !== null
                                  ? 'bg-gray-100 text-gray-400 ring-gray-200 cursor-not-allowed'
                                  : 'bg-gray-50 text-gray-700 ring-gray-200 hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700'
                              )}
                            >
                              +
                            </button>
                            {openReactionsForMessageId === message.id && processingReaction === null && (
                              <div className="ml-2 flex gap-1 rounded-full bg-white ring-1 ring-gray-200 shadow px-2 py-1 dark:bg-gray-900 dark:ring-gray-700">
                                {quickEmojis.map((e) => {
                                  const currentReaction = userReactions[message.id] !== undefined
                                    ? userReactions[message.id]
                                    : (message as MessageWithReactions).my_reactions?.[0];
                                  const isCurrentReaction = currentReaction === e;
                                  return (
                                    <button
                                      key={e}
                                      onClick={async (event) => {
                                        event.stopPropagation();
                                        event.preventDefault();
                                        if (processingReaction !== null) return;
                                        await handleAddReaction(message.id, e);
                                      }}
                                      disabled={processingReaction !== null}
                                      className={cn(
                                        "text-xl leading-none transition",
                                        processingReaction !== null ? "opacity-50 cursor-not-allowed pointer-events-none" : "hover:scale-110",
                                        isCurrentReaction && "bg-purple-100 rounded-full px-1"
                                      )}
                                    >
                                      {e}
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Inline read time for latest read own message (iMessage-style) */}
                        {isOwn && message.id === lastOwnReadMessageId && (mergedReadReceipts[message.id]?.length ?? 0) > 0 && (
                          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400 text-right pr-1">
                            {(() => {
                              const firstReceipt = mergedReadReceipts[message.id]?.[0];
                              const readAt = new Date(firstReceipt?.read_at || '');
                              if (isToday(readAt)) return `Read at ${format(readAt, 'h:mm a')}`;
                              if (isYesterday(readAt)) return `Read yesterday at ${format(readAt, 'h:mm a')}`;
                              return `Read on ${format(readAt, 'MMM d')} at ${format(readAt, 'h:mm a')}`;
                            })()}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* New message indicator */}
      {!isAtBottom && (
        <button
          onClick={() => scrollToBottom()}
          className="absolute bottom-24 right-4 bg-[#7E22CE] text-white rounded-full p-2 shadow-lg ring-1 ring-black/5 hover:bg-[#7E22CE] transition dark:bg-purple-600 dark:hover:bg-[#7E22CE]"
          aria-label="Scroll to latest messages"
        >
          <ChevronDown className="w-5 h-5" aria-hidden="true" />
        </button>
      )}

      {/* Input area */}
      <div className="border-t border-gray-200 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/70 px-3 sm:px-4 py-2 sm:py-3 dark:border-gray-800 dark:bg-gray-900/80 dark:supports-[backdrop-filter]:bg-gray-900/60">
        {typingStatus && typingStatus.userId !== currentUserId && !isReadOnly && (
          <div className="px-1 pb-1 text-xs text-gray-500 dark:text-gray-400">{otherUserName} is typing…</div>
        )}
        {isReadOnly ? (
          <div className="text-center py-2 text-sm text-gray-500">
            This lesson has ended. Chat is view-only.
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={inputMessage}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              className="flex-1 resize-none rounded-full md:rounded-2xl border border-gray-300 bg-gray-50 px-4 py-2 placeholder:text-gray-400 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 shadow-inner dark:border-gray-600 dark:bg-gray-800 dark:placeholder:text-gray-500"
              style={{ minHeight: '40px', maxHeight: '160px' }}
            />
            {/* Removed quick reaction picker next to Send to prevent accidental self-reactions */}
            <button
              onClick={handleSendMessage}
              disabled={!inputMessage.trim() || sendMessageMutation.isPending}
              className={cn(
                'rounded-full p-2 md:p-2.5 transition-colors shadow-sm',
                inputMessage.trim() && !sendMessageMutation.isPending
                  ? 'bg-[#7E22CE] text-white hover:bg-[#7E22CE] ring-1 ring-[#7E22CE]/20 dark:bg-purple-600 dark:hover:bg-[#7E22CE]'
                  : 'bg-gray-100 text-gray-400 ring-1 ring-gray-200 cursor-not-allowed dark:bg-gray-800 dark:text-gray-500 dark:ring-gray-700'
              )}
              aria-label={sendMessageMutation.isPending ? 'Sending message' : 'Send message'}
            >
              {sendMessageMutation.isPending ? (
                <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
              ) : typingStatus && typingStatus.userId === currentUserId ? (
                <span className="text-xs px-1">…</span>
              ) : (
                <Send className="w-5 h-5" aria-hidden="true" />
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
