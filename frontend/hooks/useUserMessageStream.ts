// frontend/hooks/useUserMessageStream.ts
/**
 * Single SSE connection for ALL user conversations.
 *
 * Replaces per-booking connections with one user-scoped stream.
 * Components subscribe to specific conversations via conversation_id.
 *
 * Phase 4: Per-user inbox architecture
 */

import { useRef, useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { withApiBase } from '@/lib/apiBase';
import { logger } from '@/lib/logger';
import type { SSEEvent, ConversationHandlers, SSEReadReceiptEvent } from '@/types/messaging';

const SSE_ENDPOINT = '/api/v1/messages/stream';
const RECONNECT_DELAY = 3000;
const HEARTBEAT_TIMEOUT = 45000; // 45 seconds (server sends every 30s)

export function useUserMessageStream() {
  const { isAuthenticated, user } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Map of conversation_id -> handlers
  const handlersRef = useRef<Map<string, ConversationHandlers>>(new Map());
  const eventSourceRef = useRef<EventSource | null>(null);
  const heartbeatTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Subscribe a conversation to receive events
  const subscribe = useCallback(
    (conversationId: string, handlers: ConversationHandlers) => {
      handlersRef.current.set(conversationId, handlers);
      logger.debug('[SSE] Subscribed to conversation', { conversationId });

      // Return unsubscribe function
      return () => {
        handlersRef.current.delete(conversationId);
        logger.debug('[SSE] Unsubscribed from conversation', {
          conversationId,
        });
      };
    },
    []
  );

  // Route event to appropriate handler
  const routeEvent = useCallback((event: SSEEvent) => {
    // First, notify the global handler (if subscribed)
    const globalHandlers = handlersRef.current.get('__global__');
    if (globalHandlers && event.type === 'new_message') {
      globalHandlers.onMessage?.(event.message, event.is_mine);
    }

    // Then, notify the conversation-specific handler
    const handlers = handlersRef.current.get(event.conversation_id);
    if (!handlers) {
      logger.debug('[SSE] No handler for conversation', {
        conversation_id: event.conversation_id,
        type: event.type,
      });
      return; // No subscriber for this conversation
    }

    switch (event.type) {
      case 'new_message':
        handlers.onMessage?.(event.message, event.is_mine);
        break;
      case 'typing_status':
        handlers.onTyping?.(event.user_id, event.user_name, event.is_typing);
        break;
      case 'read_receipt': {
        // Database trigger sends message_id (singular), but handler expects message_ids (array)
        // TypeScript doesn't know about message_id, so we use type assertion
        const eventWithMessageId = event as SSEReadReceiptEvent & { message_id?: string };
        const messageIds = event.message_ids || (eventWithMessageId.message_id ? [eventWithMessageId.message_id] : []);
        handlers.onReadReceipt?.(messageIds, event.reader_id);
        break;
      }
      case 'reaction_update':
        handlers.onReaction?.(event.message_id, event.emoji, event.action, event.user_id);
        break;
    }
  }, []);

  // Reset heartbeat timeout
  const resetHeartbeat = useCallback(() => {
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current);
    }
    heartbeatTimeoutRef.current = setTimeout(() => {
      // No heartbeat received, connection may be dead
      logger.warn('[SSE] Heartbeat timeout, reconnecting...');
      eventSourceRef.current?.close();
      setIsConnected(false);
    }, HEARTBEAT_TIMEOUT);
  }, []);

  // Connect to SSE
  const connect = useCallback(() => {
    if (!isAuthenticated || eventSourceRef.current) return;

    const url = withApiBase(SSE_ENDPOINT);
    logger.info('[SSE] Connecting to user inbox stream', { url });

    const eventSource = new EventSource(url, {
      withCredentials: true,
    } as EventSourceInit);

    eventSource.addEventListener('connected', () => {
      logger.info('[SSE] Connected to user inbox stream');
      setIsConnected(true);
      setConnectionError(null);
      resetHeartbeat();
    });

    eventSource.addEventListener('keep-alive', () => {
      resetHeartbeat();
    });

    eventSource.addEventListener('heartbeat', () => {
      resetHeartbeat();
    });

    // Handle all event types
    eventSource.addEventListener('new_message', (event) => {
      resetHeartbeat();
      try {
        const data: SSEEvent = JSON.parse((event as MessageEvent).data);
        routeEvent(data);
      } catch (err) {
        logger.error('[SSE] Failed to parse new_message event', { err });
      }
    });

    eventSource.addEventListener('typing_status', (event) => {
      try {
        const data: SSEEvent = JSON.parse((event as MessageEvent).data);
        routeEvent(data);
      } catch (err) {
        logger.error('[SSE] Failed to parse typing_status event', { err });
      }
    });

    eventSource.addEventListener('read_receipt', (event) => {
      try {
        const data: SSEEvent = JSON.parse((event as MessageEvent).data);
        routeEvent(data);
      } catch (err) {
        logger.error('[SSE] Failed to parse read_receipt event', { err });
      }
    });

    eventSource.addEventListener('reaction_update', (event) => {
      try {
        const data: SSEEvent = JSON.parse((event as MessageEvent).data);
        routeEvent(data);
      } catch (err) {
        logger.error('[SSE] Failed to parse reaction_update event', { err });
      }
    });

    eventSource.onerror = (err) => {
      logger.error('[SSE] Connection error', { err });
      setIsConnected(false);
      setConnectionError('Connection lost');
      eventSource.close();
      eventSourceRef.current = null;

      // Reconnect after delay
      reconnectTimeoutRef.current = setTimeout(() => {
        logger.info('[SSE] Attempting reconnect...');
        connect();
      }, RECONNECT_DELAY);
    };

    eventSourceRef.current = eventSource;
  }, [isAuthenticated, resetHeartbeat, routeEvent]);

  // Connect on mount, cleanup on unmount
  useEffect(() => {
    if (!isAuthenticated || !user) return;

    connect();

    return () => {
      if (heartbeatTimeoutRef.current) {
        clearTimeout(heartbeatTimeoutRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      logger.info('[SSE] Disconnected');
    };
  }, [connect, isAuthenticated, user]);

  return {
    isConnected,
    connectionError,
    subscribe,
  };
}
