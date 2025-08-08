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
import { format, isToday, isYesterday, isSameDay } from 'date-fns';
import { Send, Loader2, AlertCircle, WifiOff, Check, CheckCheck, ChevronDown } from 'lucide-react';
import { useSSEMessages, ConnectionStatus } from '@/hooks/useSSEMessages';
import { useMessageHistory, useSendMessage, useMarkAsRead } from '@/hooks/useMessageQueries';
import { Message } from '@/services/messageService';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';

interface ChatProps {
  bookingId: number;
  currentUserId: number;
  currentUserName: string;
  otherUserName: string;
  className?: string;
  onClose?: () => void;
}

export function Chat({
  bookingId,
  currentUserId,
  currentUserName,
  otherUserName,
  className,
  onClose,
}: ChatProps) {
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
  // Since optimistic messages have negative IDs, we only keep those that are truly optimistic
  useEffect(() => {
    if (historyData?.messages) {
      // Remove any optimistic messages that have negative IDs only
      // Real messages from the server will have positive IDs
      setOptimisticMessages(prev => prev.filter(msg => msg.id < 0));
    }
  }, [historyData]);

  // Real-time messages via SSE
  const {
    messages: realtimeMessages,
    connectionStatus,
    reconnect,
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
    const messageMap = new Map<number, Message>();

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
  }, [bookingId]);

  // Handle send message with optimistic update
  const handleSendMessage = async () => {
    const content = inputMessage.trim();
    if (!content) return;

    setInputMessage('');

    // Create optimistic message with temporary ID
    const tempId = -Date.now(); // Negative ID to distinguish from real IDs
    const optimisticMessage: Message = {
      id: tempId,
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
      setOptimisticMessages(prev => prev.filter(msg => msg.id !== tempId));

    } catch (error) {
      logger.error('Failed to send message', error);
      // Remove optimistic message on error
      setOptimisticMessages(prev => prev.filter(msg => msg.id !== tempId));
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
        className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4"
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
                  const nextSameSender = index < messages.length - 1 && messages[index + 1].sender_id === message.sender_id;

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
                          'max-w-[75%] sm:max-w-[60%]',
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
                            'rounded-2xl px-4 py-2 break-words shadow-sm select-text',
                            isOwn
                              ? 'bg-gradient-to-tr from-blue-600 to-blue-500 text-white ring-1 ring-blue-500/10'
                              : 'bg-white text-gray-900 ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:ring-gray-700'
                          )}
                        >
                          <p className="whitespace-pre-wrap">{message.content}</p>
                          <div className={cn(
                            'flex items-center justify-end mt-1 space-x-1',
                            isOwn ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400'
                          )}>
                            <span className="text-xs">
                              {formatMessageDate(message.created_at)}
                            </span>
                            {isOwn && (
                              <CheckCheck className="w-3 h-3" />
                            )}
                          </div>
                        </div>
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
          className="absolute bottom-24 right-4 bg-blue-600 text-white rounded-full p-2 shadow-lg ring-1 ring-black/5 hover:bg-blue-700 transition dark:bg-blue-500 dark:hover:bg-blue-600"
        >
          <ChevronDown className="w-5 h-5" />
        </button>
      )}

      {/* Input area */}
      <div className="border-t border-gray-200 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/70 px-4 py-3 dark:border-gray-800 dark:bg-gray-900/80 dark:supports-[backdrop-filter]:bg-gray-900/60">
        <div className="flex items-end space-x-2">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="flex-1 resize-none rounded-full md:rounded-2xl border border-gray-200 bg-gray-50 px-4 py-2 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/40 shadow-inner dark:border-gray-700 dark:bg-gray-800 dark:placeholder:text-gray-500"
            style={{ minHeight: '44px', maxHeight: '120px' }}
          />
          <button
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || sendMessage.isPending}
            className={cn(
              'rounded-full p-2 md:p-2.5 transition-colors shadow-sm',
              inputMessage.trim() && !sendMessage.isPending
                ? 'bg-blue-600 text-white hover:bg-blue-700 ring-1 ring-blue-500/20 dark:bg-blue-500 dark:hover:bg-blue-600'
                : 'bg-gray-100 text-gray-400 ring-1 ring-gray-200 cursor-not-allowed dark:bg-gray-800 dark:text-gray-500 dark:ring-gray-700'
            )}
          >
            {sendMessage.isPending ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
