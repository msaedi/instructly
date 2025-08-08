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
import { Send, Loader2, AlertCircle, WifiOff, Check, CheckCheck } from 'lucide-react';
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

  // Combine history and real-time messages
  const allMessages = [
    ...(historyData?.messages || []),
    ...realtimeMessages.filter(
      (rtMsg) => !historyData?.messages.some((hMsg) => hMsg.id === rtMsg.id)
    ),
  ].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

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

  // Handle send message
  const handleSendMessage = async () => {
    const content = inputMessage.trim();
    if (!content) return;

    setInputMessage('');

    try {
      await sendMessage.mutateAsync({
        booking_id: bookingId,
        content,
      });
      scrollToBottom();
    } catch (error) {
      logger.error('Failed to send message', error);
      // Restore message on error
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
      <div className={cn('flex items-center justify-center h-full', className)}>
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
    <div className={cn('flex flex-col h-full bg-white', className)}>
      {/* Connection status */}
      <ConnectionIndicator />

      {/* Messages container */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-4"
      >
        {allMessages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            <p>No messages yet. Start the conversation!</p>
          </div>
        ) : (
          <>
            {Object.entries(messagesByDate).map(([date, messages]) => (
              <div key={date}>
                {/* Date separator */}
                <div className="flex items-center justify-center my-4">
                  <div className="bg-gray-100 rounded-full px-3 py-1 text-xs text-gray-600">
                    {getDateSeparator(messages[0].created_at)}
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
                        !showSender && 'mt-1'
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
                            'text-xs text-gray-500 mb-1',
                            isOwn ? 'text-right mr-2' : 'ml-2'
                          )}>
                            {isOwn ? currentUserName : otherUserName}
                          </div>
                        )}

                        {/* Message bubble */}
                        <div
                          className={cn(
                            'rounded-2xl px-4 py-2 break-words',
                            isOwn
                              ? 'bg-blue-600 text-white'
                              : 'bg-gray-100 text-gray-900'
                          )}
                        >
                          <p className="whitespace-pre-wrap">{message.content}</p>
                          <div className={cn(
                            'flex items-center justify-end mt-1 space-x-1',
                            isOwn ? 'text-blue-100' : 'text-gray-500'
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
          className="absolute bottom-20 right-4 bg-white border border-gray-300 rounded-full p-2 shadow-lg"
        >
          <svg
            className="w-5 h-5 text-gray-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </button>
      )}

      {/* Input area */}
      <div className="border-t bg-white px-4 py-3">
        <div className="flex items-end space-x-2">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="flex-1 resize-none rounded-2xl border border-gray-300 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            style={{ minHeight: '40px', maxHeight: '120px' }}
          />
          <button
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || sendMessage.isPending}
            className={cn(
              'rounded-full p-2 transition-colors',
              inputMessage.trim() && !sendMessage.isPending
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
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
