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
import { Send, Loader2, AlertCircle, WifiOff, ChevronDown } from 'lucide-react';
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
  useDeleteMessage,
} from '@/src/api/services/messages';
import { queryKeys } from '@/src/api/queryKeys';
import type { MessageResponse } from '@/src/api/generated/instructly.schemas';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';
import { MessageBubble, normalizeStudentMessage, formatRelativeTimestamp, useReactions, useReadReceipts, useLiveTimestamp, useSSEHandlers, type NormalizedMessage, type NormalizedReaction, type ReactionMutations, type ReadReceiptEntry } from '@/components/messaging';

// Connection status enum (internal to Chat component)
enum ConnectionStatus {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  ERROR = 'error',
  RECONNECTING = 'reconnecting',
}

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
  const deleteMessageMutation = useDeleteMessage();
  const addReactionMutation = useAddReaction();
  const removeReactionMutation = useRemoveReaction();
  const sendTypingMutation = useSendTypingIndicator();
  const lastMarkedUnreadByBookingRef = useRef<Record<string, string | null>>({});
  const typingDebounceRef = useRef<NodeJS.Timeout | null>(null);

  // Real-time messages via SSE (Phase 4: per-user inbox)
  const { subscribe, isConnected, connectionError } = useMessageStream();
  const [realtimeMessages, setRealtimeMessages] = useState<MessageResponse[]>([]);
  const [reactionDeltas, setReactionDeltas] = useState<
    Record<string, Record<string, number>>
  >({});

  // Shared SSE handlers for typing and read receipts
  const {
    typingStatus,
    sseReadReceipts,
    handleSSETyping,
    handleSSEReadReceipt,
  } = useSSEHandlers();

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

  const handleMessageDeleted = useCallback((messageId: string, _deletedBy: string) => {
    logger.debug('[MSG-DEBUG] handleMessageDeleted CALLED', {
      messageId,
      currentBookingId: bookingId,
    });

    setRealtimeMessages((prev) => {
      const messageIndex = prev.findIndex((m) => m.id === messageId);
      if (messageIndex !== -1) {
        const updated = [...prev];
        updated[messageIndex] = {
          ...updated[messageIndex]!,
          is_deleted: true,
          deleted_at: new Date().toISOString(),
          content: 'This message was deleted',
        } as MessageResponse;
        return updated;
      }
      return prev;
    });

    void queryClient.invalidateQueries({
      queryKey: queryKeys.messages.history(bookingId),
      exact: false,
    });
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
      onReadReceipt: handleSSEReadReceipt,
      onReaction: handleReaction,
      onMessageEdited: handleMessageEdited,
      onMessageDeleted: handleMessageDeleted,
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
    };
  }, [bookingId, subscribe, handleSSEMessage, handleSSETyping, handleSSEReadReceipt, handleReaction, handleMessageEdited, handleMessageDeleted, queryClient]);

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
    // SSE now echoes messages to sender with is_mine flag; realtime always wins for freshness
    realtimeMessages.forEach(msg => {
      messageMap.set(msg.id, msg);
      logger.debug('[MSG-DEBUG] Chat: allMessages - applied realtime message', {
        messageId: msg.id,
        content: msg.content?.substring(0, 30),
      });
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

  // Shared reaction management hook
  const reactionMutations: ReactionMutations = React.useMemo(
    () => ({
      addReaction: (params) => addReactionMutation.mutateAsync(params),
      removeReaction: (params) => removeReactionMutation.mutateAsync(params),
    }),
    [addReactionMutation, removeReactionMutation]
  );

  const {
    userReactions,
    processingReaction,
    handleReaction: handleAddReaction,
    hasReacted,
  } = useReactions({
    messages: allMessages as MessageWithReactions[],
    mutations: reactionMutations,
    onReactionComplete: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.messages.history(bookingId),
        exact: false,
      });
    },
    debug: false,
  });

  // Shared read receipt management hook
  const { mergedReadReceipts, lastReadMessageId: lastOwnReadMessageId } = useReadReceipts<MessageResponse>({
    messages: allMessages,
    sseReadReceipts,
    currentUserId,
    getReadBy: (m) => m.read_by as ReadReceiptEntry[] | null | undefined,
    isOwnMessage: (m) => m.sender_id === currentUserId,
    getCreatedAt: (m) => new Date(m.created_at),
  });

  // Live timestamp ticker - triggers re-render every minute for relative timestamps
  const tick = useLiveTimestamp();

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
    if (typingDebounceRef.current) {
      clearTimeout(typingDebounceRef.current);
      typingDebounceRef.current = null;
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
    if (typingDebounceRef.current) clearTimeout(typingDebounceRef.current);
    typingDebounceRef.current = setTimeout(() => {
      void handleTyping();
    }, 300); // 300ms debounce for more responsive typing indicator
  };

  // Quick reaction emojis
  const quickEmojis = ['👍', '❤️', '😊', '😮', '🎉'];

  const canEditMessage = (message: MessageResponse): boolean => {
    if (message.sender_id !== currentUserId) return false;
    const isDeleted = Boolean((message as { is_deleted?: boolean }).is_deleted);
    if (isDeleted) return false;
    const created = new Date(message.created_at).getTime();
    const now = Date.now();
    const diffMinutes = (now - created) / 60000;
    return diffMinutes <= editWindowMinutes;
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

  // Build normalized messages for shared bubble
  const normalizedMessages = React.useMemo<NormalizedMessage[]>(() => {
    return allMessages.map((message) => {
      const isOwn = message.sender_id === currentUserId;
      const timestampLabel = formatRelativeTimestamp(message.created_at);
      const receipts = mergedReadReceipts[message.id] || [];
      const readStatus: 'sent' | 'delivered' | 'read' | undefined = isOwn
        ? (receipts.length > 0 ? 'read' : message.delivered_at ? 'delivered' : 'sent')
        : undefined;

      let readTimestampLabel: string | undefined;
      if (isOwn && message.id === lastOwnReadMessageId && receipts.length > 0) {
        const readAt = new Date(receipts[0]?.read_at || '');
        if (isToday(readAt)) readTimestampLabel = `Read at ${format(readAt, 'h:mm a')}`;
        else if (isYesterday(readAt)) readTimestampLabel = `Read yesterday at ${format(readAt, 'h:mm a')}`;
        else readTimestampLabel = `Read on ${format(readAt, 'MMM d')} at ${format(readAt, 'h:mm a')}`;
      }

      const baseReactions = (message as MessageWithReactions).reactions || {};
      const displayReactions: Record<string, number> = { ...baseReactions };
      const localReaction = userReactions[message.id];
      const serverReaction = (message as MessageWithReactions).my_reactions?.[0];

      if (localReaction !== undefined && localReaction !== serverReaction) {
        if (serverReaction) {
          displayReactions[serverReaction] = Math.max(0, (displayReactions[serverReaction] || 0) - 1);
          if (displayReactions[serverReaction] === 0) delete displayReactions[serverReaction];
        }
        if (localReaction) {
          displayReactions[localReaction] = (displayReactions[localReaction] || 0) + 1;
        }
      }

      const delta = reactionDeltas[message.id];
      if (delta) {
        Object.entries(delta).forEach(([emoji, change]) => {
          displayReactions[emoji] = Math.max(0, (displayReactions[emoji] || 0) + change);
          if (displayReactions[emoji] === 0) delete displayReactions[emoji];
        });
      }

      const reactions: NormalizedReaction[] = Object.entries(displayReactions)
        .filter(([, count]) => count > 0)
        .map(([emoji, count]) => ({
          emoji,
          count,
          isMine: hasReacted(message.id, emoji),
        }));

      const currentReaction =
        localReaction !== undefined
          ? localReaction
          : (message as MessageWithReactions).my_reactions?.[0] ?? null;

      return normalizeStudentMessage(message, currentUserId, {
        reactions,
        currentUserReaction: currentReaction,
        timestampLabel,
        readStatus,
        readTimestampLabel,
      });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps -- tick triggers periodic re-render for live timestamps
  }, [allMessages, currentUserId, mergedReadReceipts, lastOwnReadMessageId, userReactions, reactionDeltas, hasReacted, tick]);

  // Group messages by date (normalized)
  const messagesByDate = React.useMemo(() => {
    return normalizedMessages.reduce((groups, message) => {
      const date = message.timestamp.toDateString();
      if (!groups[date]) groups[date] = [];
      groups[date].push(message);
      return groups;
    }, {} as Record<string, NormalizedMessage[]>);
  }, [normalizedMessages]);

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
                      {getDateSeparator(messages[0]?.timestamp?.toISOString() || '')}
                    </span>
                  </div>
                </div>

                {/* Messages for this date */}
                {messages.map((message, index) => {
                  const raw = message._raw as MessageResponse | undefined;
                  const prevRaw = messages[index - 1]?._raw as MessageResponse | undefined;
                  const showSender = index === 0 || (raw && prevRaw && raw.sender_id !== prevRaw.sender_id);
                  const senderLabel = message.isOwn ? currentUserName : otherUserName;
                  return (
                    <div
                      key={message.id}
                      className={cn(
                        'flex',
                        message.isOwn ? 'justify-end' : 'justify-start',
                        !showSender && 'mt-1.5'
                      )}
                    >
                      <div className={cn('relative max-w-[82%] xs:max-w-[78%] sm:max-w-[60%]', message.isOwn ? 'items-end' : 'items-start')}>
                        {showSender && (
                          <div className={cn('text-xs text-gray-500 dark:text-gray-400 mb-1', message.isOwn ? 'text-right mr-2' : 'ml-2')}>
                            {senderLabel}
                          </div>
                        )}
                        <MessageBubble
                          message={message}
                          canEdit={message.isOwn && raw ? canEditMessage(raw) : false}
                          canDelete={message.isOwn && raw ? canEditMessage(raw) : false}
                          canReact={!message.isOwn && !message.isDeleted}
                          showReadReceipt={message.isOwn}
                          onEdit={async (messageId, newContent) => {
                            const target = allMessages.find((m) => m.id === messageId);
                            if (!target || !canEditMessage(target)) return;
                            await editMessageMutation.mutateAsync({
                              messageId,
                              data: { content: newContent },
                            });
                          }}
                          onDelete={async (messageId) => {
                            const target = allMessages.find((m) => m.id === messageId);
                            if (!target || !canEditMessage(target)) return;
                            await deleteMessageMutation.mutateAsync({ messageId });
                            setRealtimeMessages((prev) => {
                              const idx = prev.findIndex((m) => m.id === messageId);
                              if (idx === -1) return prev;
                              const updated = [...prev];
                              updated[idx] = {
                                ...updated[idx]!,
                                is_deleted: true,
                                deleted_at: new Date().toISOString(),
                                content: 'This message was deleted',
                              } as MessageResponse;
                              return updated;
                            });
                            void queryClient.invalidateQueries({
                              queryKey: queryKeys.messages.history(bookingId),
                              exact: false,
                            });
                          }}
                          onReact={async (messageId, emoji) => {
                            if (processingReaction !== null) return;
                            await handleAddReaction(messageId, emoji);
                          }}
                          reactionBusy={processingReaction !== null}
                          side={message.isOwn ? 'right' : 'left'}
                          quickEmojis={quickEmojis}
                        />
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
