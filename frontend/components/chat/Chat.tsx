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
import { useSSEMessages, ConnectionStatus } from '@/hooks/useSSEMessages';
import { useMessageHistory, useSendMessage, useMarkAsRead } from '@/hooks/useMessageQueries';
import { Message } from '@/services/messageService';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';

// Extended message type with reactions
interface MessageWithReactions extends Message {
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
  // Config: fetched from backend to avoid drift
  const [editWindowMinutes, setEditWindowMinutes] = useState<number>(5);
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
  useEffect(() => {
    (async () => {
      try {
        const { messageService } = await import('@/services/messageService');
        const cfg = await messageService.getMessageConfig();
        if (cfg?.edit_window_minutes) setEditWindowMinutes(cfg.edit_window_minutes);
      } catch {}
    })();
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

  // Clear optimistic messages when history is refreshed
  // Since optimistic messages have negative timestamp IDs (as strings), we only keep those that are truly optimistic
  useEffect(() => {
    if (historyData?.messages) {
      // Keep only optimistic messages (those with IDs starting with '-')
      // Real messages from the server will have ULID strings
      setOptimisticMessages(prev => prev.filter(msg => msg.id.startsWith('-')));
    }
  }, [historyData]);

  // Real-time messages via SSE
  const {
    messages: realtimeMessages,
    connectionStatus,
    reconnect,
    readReceipts,
    typingStatus,
    reactionDeltas,
  } = useSSEMessages({
    bookingId,
    enabled: true,
    onMessage: (message) => {
      // Mark message as read if it's from the other user
      if (message.sender_id !== currentUserId) {
        markAsRead.mutate({ message_ids: [message.id] });
      }
    },
  });

  // Mutations
  const sendMessage = useSendMessage();
  const markAsRead = useMarkAsRead();

  // State for optimistically added messages (sent by current user)
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);

  // Combine history, optimistic, and real-time messages with deduplication
  const allMessages = React.useMemo(() => {
    const messageMap = new Map<string, Message>();

    // Add history messages
    (historyData?.messages || []).forEach(msg => {
      messageMap.set(msg.id, msg);
    });

    // Add real-time messages (only if not already in history)
    realtimeMessages.forEach(msg => {
      if (!messageMap.has(msg.id)) {
        messageMap.set(msg.id, msg);
      }
    });

    // Add optimistic messages (they have negative IDs so won't conflict)
    optimisticMessages.forEach(msg => {
      messageMap.set(msg.id, msg);
    });

    // Convert to array and sort by time
    return Array.from(messageMap.values()).sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
  }, [historyData?.messages, realtimeMessages, optimisticMessages]);

  // Build a stable read map derived from server-provided read_by and live receipts
  const mergedReadReceipts = React.useMemo(() => {
    const map: Record<string, Array<{ user_id: string; read_at: string }>> = { ...readReceipts };
    for (const m of allMessages) {
      if (m.read_by && Array.isArray(m.read_by)) {
        const existing = map[m.id] || [];
        const combined = [...existing];
        for (const r of m.read_by) {
          if (!combined.find(x => x.user_id === r.user_id && x.read_at === r.read_at)) {
            if (r.user_id && r.read_at) combined.push({ user_id: r.user_id, read_at: r.read_at });
          }
        }
        map[m.id] = combined;
      }
    }
    return map;
  }, [allMessages, readReceipts]);

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

  // Mark messages as read when component mounts
  useEffect(() => {
    if (bookingId) {
      markAsRead.mutate({ booking_id: bookingId });
    }
  }, [bookingId, markAsRead]);

  // Handle send message with optimistic update
  const handleSendMessage = async () => {
    const content = inputMessage.trim();
    if (!content) return;

    setInputMessage('');

    // Create optimistic message with temporary ID
    const tempId = -Date.now(); // Negative ID to distinguish from real IDs
    const optimisticMessage: Message = {
      id: tempId.toString(),
      booking_id: bookingId,
      sender_id: currentUserId,
      content,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      is_deleted: false,
      sender: {
        id: currentUserId,
        full_name: currentUserName,
        email: '', // Not needed for display
      },
    };

    // Add optimistic message immediately
    setOptimisticMessages(prev => [...prev, optimisticMessage]);
    scrollToBottom();

    try {
      await sendMessage.mutateAsync({
        booking_id: bookingId,
        content,
      });

      // Remove the optimistic message after successful send
      // The real message will appear in historyData after React Query invalidation
      setOptimisticMessages(prev => prev.filter(msg => msg.id !== tempId.toString()));

    } catch (error) {
      logger.error('Failed to send message', error);
      // Remove optimistic message on error
      setOptimisticMessages(prev => prev.filter(msg => msg.id !== tempId.toString()));
      // Restore input message on error
      setInputMessage(content);
    }
  };

  // Handle enter key (send on Enter, new line on Shift+Enter)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Typing indicator: send best-effort signal with debounce (1s)
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const handleTyping = async () => {
    try {
      // @ts-ignore lazy import to avoid circular
      const { messageService } = await import('@/services/messageService');
      await messageService.sendTyping(bookingId);
    } catch {}
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputMessage(e.target.value);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => {
      handleTyping();
    }, 1000);
  };

  // Quick reactions toggle per-message
  const [openReactionsForMessageId, setOpenReactionsForMessageId] = useState<string | null>(null);
  const [processingReaction, setProcessingReaction] = useState<string | null>(null);
  const quickEmojis = ['👍', '❤️', '😊', '😮', '🎉'];
  const handleAddReaction = async (messageId: string, emoji: string) => {
    // For optimistic/temporary messages with negative IDs
    if (messageId.startsWith('-')) {
      return;
    }

    // Prevent multiple simultaneous reactions GLOBALLY (not just per message)
    if (processingReaction !== null) {
      logger.warn(`Already processing reaction, ignoring new reaction request`);
      return;
    }

    try {
      setProcessingReaction(messageId);
      const { messageService } = await import('@/services/messageService');

      // Optimistic UX: close popover immediately
      setOpenReactionsForMessageId(null);

      // Find the message to check current user's reaction
      const message = allMessages.find(m => m.id === messageId);
      if (!message) {
        logger.error(`Message ${messageId} not found`);
        return;
      }

      // Get current state
      const myReactions = (message as MessageWithReactions)?.my_reactions || [];
      const localReaction = userReactions[messageId];
      const currentReaction = localReaction !== undefined ? localReaction : myReactions[0];

      logger.info(`Reaction state for message ${messageId}:`, {
        requestedEmoji: emoji,
        serverReactions: myReactions,
        localReaction,
        currentReaction
      });

      // If user is trying to add a reaction when they already have one (and it's different)
      // Force remove the old one first
      if (currentReaction && currentReaction !== emoji) {
        logger.info(`User already has reaction ${currentReaction}, will replace with ${emoji}`);
        // Update local state immediately to show the change
        setUserReactions(prev => ({ ...prev, [messageId]: emoji }));

        // Remove old reaction
        const removed = await messageService.removeReaction(messageId, currentReaction);
        if (!removed) {
          logger.error(`Failed to remove old reaction ${currentReaction}`);
          // Revert local state
          setUserReactions(prev => ({ ...prev, [messageId]: currentReaction }));
          return;
        }

        // Add new reaction
        const added = await messageService.addReaction(messageId, emoji);
        if (!added) {
          logger.error(`Failed to add new reaction ${emoji}`);
          // Revert to no reaction since we removed the old one
          setUserReactions(prev => ({ ...prev, [messageId]: null }));
          return;
        }
      } else if (currentReaction === emoji) {
        // Toggle off - remove the reaction
        logger.info(`Toggling off reaction ${emoji} from message ${messageId}`);
        setUserReactions(prev => ({ ...prev, [messageId]: null }));

        const removed = await messageService.removeReaction(messageId, emoji);
        if (!removed) {
          logger.error(`Failed to remove reaction ${emoji}`);
          // Revert local state
          setUserReactions(prev => ({ ...prev, [messageId]: emoji }));
        }
      } else {
        // No current reaction, add the new one
        logger.info(`Adding new reaction ${emoji} to message ${messageId}`);
        setUserReactions(prev => ({ ...prev, [messageId]: emoji }));

        const added = await messageService.addReaction(messageId, emoji);
        if (!added) {
          logger.error(`Failed to add reaction ${emoji}`);
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
            await messageService.removeReaction(messageId, extraEmoji);
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
  const startEdit = (message: Message) => {
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
      const { messageService } = await import('@/services/messageService');
      // TypeScript should know editingMessageId is string here due to the guard above
      const messageId: string = editingMessageId;
      const ok = await messageService.editMessage(messageId, editingContent.trim());
      if (ok) {
        setEditingMessageId(null);
        setEditingContent("");
      }
    } finally {
      setIsSavingEdit(false);
    }
  };

  const canEditMessage = (message: Message): boolean => {
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
            keepEmoji: myReactions[0],
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
        const { messageService } = await import('@/services/messageService');
        for (const cleanup of cleanupMessages) {
          for (const emojiToRemove of cleanup.removeEmojis) {
            try {
              await messageService.removeReaction(cleanup.messageId, emojiToRemove);
              logger.info(`Cleaned up extra reaction ${emojiToRemove} from message ${cleanup.messageId}`);
            } catch (error) {
              logger.error(`Failed to clean up reaction ${emojiToRemove}`, error);
            }
          }
        }
      })();
    }
  }, [allMessages, userReactions]); // Only re-run when messages or reactions change

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _toggleReactionLocal = (message: Message, emoji: string) => {
    setUserReactions(prev => {
      const currentReaction = prev[message.id];

      // If clicking the same emoji, remove it (toggle off)
      if (currentReaction === emoji) {
        return { ...prev, [message.id]: null };
      }

      // Otherwise, set this as the only reaction
      return { ...prev, [message.id]: emoji };
    });
  };

  const isEmojiMyReacted = (message: Message, emoji: string): boolean => {
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
  }, {} as Record<string, Message[]>);

  // Connection status component
  const ConnectionIndicator = () => {
    if (connectionStatus === ConnectionStatus.CONNECTED) {
      return null;
    }

    return (
      <div className={cn(
        'flex items-center justify-center py-2 px-4 text-sm',
        connectionStatus === ConnectionStatus.CONNECTING && 'bg-blue-50 text-blue-700',
        connectionStatus === ConnectionStatus.RECONNECTING && 'bg-yellow-50 text-yellow-700',
        connectionStatus === ConnectionStatus.ERROR && 'bg-red-50 text-red-700',
        connectionStatus === ConnectionStatus.DISCONNECTED && 'bg-gray-50 text-gray-700'
      )}>
        {connectionStatus === ConnectionStatus.CONNECTING && (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Connecting...
          </>
        )}
        {connectionStatus === ConnectionStatus.RECONNECTING && (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Reconnecting...
          </>
        )}
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
                      {getDateSeparator(messages[0].created_at)}
                    </span>
                  </div>
                </div>

                {/* Messages for this date */}
                {messages.map((message, index) => {
                  const isOwn = message.sender_id === currentUserId;
                  const showSender = index === 0 ||
                    messages[index - 1].sender_id !== message.sender_id;

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
                              ? 'bg-gradient-to-tr from-purple-700 to-purple-600 text-white ring-1 ring-purple-500/10'
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
                                  className={cn('w-full resize-none rounded-md px-2 py-1 text-[15px] leading-5 outline-none focus:ring-purple-500 focus:border-purple-500', isOwn ? 'bg-transparent text-white placeholder:text-blue-100' : 'bg-transparent text-gray-900 placeholder:text-gray-400')}
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
                              // Show double check if any read receipt exists for this message
                              (mergedReadReceipts[message.id]?.length ?? 0) > 0 ? (
                                <CheckCheck className="w-3 h-3" />
                              ) : (
                                <Check className="w-3 h-3" />
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
                                    mine ? 'bg-purple-700 text-white ring-purple-700' : (isOwn ? 'bg-purple-50 text-purple-700 ring-purple-200' : 'bg-gray-50 text-gray-700 ring-gray-200'),
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
                              const readAt = new Date(mergedReadReceipts[message.id][0].read_at);
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
          className="absolute bottom-24 right-4 bg-purple-700 text-white rounded-full p-2 shadow-lg ring-1 ring-black/5 hover:bg-purple-800 transition dark:bg-purple-600 dark:hover:bg-purple-700"
        >
          <ChevronDown className="w-5 h-5" />
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
              className="flex-1 resize-none rounded-full md:rounded-2xl border border-gray-300 bg-gray-50 px-4 py-2 placeholder:text-gray-400 focus:outline-none focus:ring-purple-500 focus:border-purple-500 shadow-inner dark:border-gray-600 dark:bg-gray-800 dark:placeholder:text-gray-500"
              style={{ minHeight: '40px', maxHeight: '160px' }}
            />
            {/* Removed quick reaction picker next to Send to prevent accidental self-reactions */}
            <button
              onClick={handleSendMessage}
              disabled={!inputMessage.trim() || sendMessage.isPending}
              className={cn(
                'rounded-full p-2 md:p-2.5 transition-colors shadow-sm',
                inputMessage.trim() && !sendMessage.isPending
                  ? 'bg-purple-700 text-white hover:bg-purple-800 ring-1 ring-purple-500/20 dark:bg-purple-600 dark:hover:bg-purple-700'
                  : 'bg-gray-100 text-gray-400 ring-1 ring-gray-200 cursor-not-allowed dark:bg-gray-800 dark:text-gray-500 dark:ring-gray-700'
              )}
            >
              {sendMessage.isPending ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : typingStatus && typingStatus.userId === currentUserId ? (
                <span className="text-xs px-1">…</span>
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
