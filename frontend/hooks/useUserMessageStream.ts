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
import type {
  SSEEvent,
  ConversationHandlers,
  SSEReadReceiptEvent,
  SSEMessageEditedEvent,
  SSEMessageDeletedEvent,
} from '@/types/messaging';

const SSE_ENDPOINT = '/api/v1/messages/stream';
const RECONNECT_DELAY = 3000;
const HEARTBEAT_TIMEOUT = 45000; // 45 seconds (server sends every 10s, 4.5x buffer)

// [MSG-DEBUG] Helper to get current timestamp
const debugTimestamp = () => new Date().toISOString();

export function useUserMessageStream() {
  const { isAuthenticated, user } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // [MSG-DEBUG] Log hook initialization and auth state changes
  logger.debug('[MSG-DEBUG] useUserMessageStream hook called', {
    isAuthenticated,
    hasUser: !!user,
    userId: user?.id,
    timestamp: debugTimestamp(),
  });

  // Map of conversation_id -> handlers
  const handlersRef = useRef<Map<string, ConversationHandlers>>(new Map());
  const eventSourceRef = useRef<EventSource | null>(null);
  const heartbeatTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Deduplication: Track recently processed message IDs to prevent duplicates
  // during reconnect race conditions (catch-up + Redis subscription overlap)
  const seenMessageIdsRef = useRef<Set<string>>(new Set());
  const MAX_SEEN_MESSAGE_IDS = 200;
  const PRUNE_TO_SIZE = 100;

  // Subscribe a conversation to receive events
  const subscribe = useCallback(
    (conversationId: string, handlers: ConversationHandlers) => {
      logger.debug('[MSG-DEBUG] SSE: subscribe() called', {
        conversationId,
        hasOnMessage: !!handlers.onMessage,
        hasOnTyping: !!handlers.onTyping,
        hasOnReadReceipt: !!handlers.onReadReceipt,
        currentSubscribers: Array.from(handlersRef.current.keys()),
        timestamp: debugTimestamp(),
      });
      handlersRef.current.set(conversationId, handlers);
      logger.debug('[MSG-DEBUG] SSE: Subscription added', {
        conversationId,
        allSubscribers: Array.from(handlersRef.current.keys()),
        timestamp: debugTimestamp(),
      });

      // Return unsubscribe function
      return () => {
        logger.debug('[MSG-DEBUG] SSE: unsubscribe() called', {
          conversationId,
          timestamp: debugTimestamp(),
        });
        handlersRef.current.delete(conversationId);
      };
    },
    []
  );

  // Route event to appropriate handler
  const routeEvent = useCallback((event: SSEEvent) => {
    logger.debug('[MSG-DEBUG] SSE: routeEvent() called', {
      eventType: event.type,
      conversationId: event.conversation_id,
      allSubscribers: Array.from(handlersRef.current.keys()),
      timestamp: debugTimestamp(),
    });

    // Deduplicate new_message events to prevent duplicates during reconnect
    // (catch-up query + Redis subscription can both deliver the same message)
    if (event.type === 'new_message' && event.message?.id) {
      const messageId = event.message.id;
      if (seenMessageIdsRef.current.has(messageId)) {
        logger.debug('[MSG-DEBUG] SSE: Skipping duplicate message', {
          messageId,
          timestamp: debugTimestamp(),
        });
        return;
      }

      // Track this message ID
      seenMessageIdsRef.current.add(messageId);

      // Prune set to prevent unbounded growth
      if (seenMessageIdsRef.current.size > MAX_SEEN_MESSAGE_IDS) {
        const idsArray = Array.from(seenMessageIdsRef.current);
        seenMessageIdsRef.current = new Set(idsArray.slice(-PRUNE_TO_SIZE));
      }
    }

    // First, notify the global handler (if subscribed)
    const globalHandlers = handlersRef.current.get('__global__');
    if (globalHandlers) {
      if (event.type === 'new_message') {
        logger.debug('[MSG-DEBUG] SSE: Calling global handler for new_message');
        globalHandlers.onMessage?.(event.message, event.is_mine);
      } else if (event.type === 'message_edited') {
        logger.debug('[MSG-DEBUG] SSE: Calling global handler for message_edited');
        const editEvent = event as SSEMessageEditedEvent;
        if (globalHandlers.onMessageEdited && editEvent.data?.content) {
          globalHandlers.onMessageEdited(
            editEvent.message_id,
            editEvent.data.content,
            editEvent.editor_id
          );
        }
      }
    }

    // Find handler: try conversation_id first, then fall back to booking_id
    // This handles the mismatch where frontend subscribes with booking_id
    // but some events (like new_message) have the real conversation_id
    let handlers = handlersRef.current.get(event.conversation_id);

    // Fallback: check booking_id from event payload (for new_message events)
    if (!handlers && event.type === 'new_message' && event.booking_id) {
      handlers = handlersRef.current.get(event.booking_id);
      if (handlers) {
        logger.debug('[MSG-DEBUG] SSE: Found handler via booking_id fallback', {
          conversationId: event.conversation_id,
          bookingId: event.booking_id,
          timestamp: debugTimestamp(),
        });
      }
    }

    if (!handlers) {
      logger.debug('[MSG-DEBUG] SSE: No handler found for conversation', {
        conversationId: event.conversation_id,
        bookingId: event.type === 'new_message' ? event.booking_id : undefined,
        availableSubscribers: Array.from(handlersRef.current.keys()),
        timestamp: debugTimestamp(),
      });
      return; // No subscriber for this conversation - this is expected behavior
    }

    logger.debug('[MSG-DEBUG] SSE: Handler found, routing event', {
      eventType: event.type,
      conversationId: event.conversation_id,
      hasOnMessage: !!handlers.onMessage,
      timestamp: debugTimestamp(),
    });

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
      case 'message_edited': {
        const editEvent = event as SSEMessageEditedEvent;
        // DEBUG: Check if handler exists
        logger.debug('[MSG-DEBUG] SSE: message_edited handler check', {
          hasHandler: !!handlers.onMessageEdited,
          conversationId: editEvent.conversation_id,
          messageId: editEvent.message_id,
          hasContent: !!editEvent.data?.content,
        });
        if (handlers.onMessageEdited && editEvent.data?.content) {
          logger.debug('[MSG-DEBUG] SSE: CALLING onMessageEdited handler');
          handlers.onMessageEdited(editEvent.message_id, editEvent.data.content, editEvent.editor_id);
        } else {
          logger.debug('[MSG-DEBUG] SSE: NOT calling handler', {
            reason: !handlers.onMessageEdited ? 'no handler registered' : 'no content in payload',
          });
        }
        break;
      }
      case 'message_deleted': {
        const deleteEvent = event as SSEMessageDeletedEvent;
        handlers.onMessageDeleted?.(deleteEvent.message_id, deleteEvent.deleted_by);
        break;
      }
    }
  }, []);

  // Ref to store connect function for use in heartbeat timeout
  const connectRef = useRef<(() => void) | null>(null);

  // Reset heartbeat timeout
  const resetHeartbeat = useCallback(() => {
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current);
    }
    heartbeatTimeoutRef.current = setTimeout(() => {
      // No heartbeat received, connection may be dead
      logger.warn('[SSE] Heartbeat timeout, reconnecting...');
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;  // Clear ref so connect() doesn't skip
      }
      setIsConnected(false);
      setConnectionError('Heartbeat timeout');

      // Schedule reconnect after delay (same pattern as error handler)
      logger.debug('[MSG-DEBUG] SSE: Scheduling reconnect after heartbeat timeout', {
        delayMs: RECONNECT_DELAY,
        timestamp: debugTimestamp(),
      });
      reconnectTimeoutRef.current = setTimeout(() => {
        logger.debug('[MSG-DEBUG] SSE: Attempting reconnect after heartbeat timeout...', {
          timestamp: debugTimestamp(),
        });
        logger.info('[SSE] Attempting reconnect after heartbeat timeout...');
        if (connectRef.current) {
          connectRef.current();
        }
      }, RECONNECT_DELAY);
    }, HEARTBEAT_TIMEOUT);
  }, []);

  // Connect to SSE
  const connect = useCallback(() => {
    if (!isAuthenticated || eventSourceRef.current) {
      logger.debug('[MSG-DEBUG] SSE: Skipping connect', {
        isAuthenticated,
        hasExistingConnection: !!eventSourceRef.current,
        timestamp: debugTimestamp()
      });
      return;
    }

    const url = withApiBase(SSE_ENDPOINT);
    logger.debug('[MSG-DEBUG] SSE: Attempting connection', {
      url,
      timestamp: debugTimestamp()
    });
    logger.info('[SSE] Connecting to user inbox stream', { url });

    const eventSource = new EventSource(url, {
      withCredentials: true,
    } as EventSourceInit);

    logger.debug('[MSG-DEBUG] SSE: EventSource created', {
      readyState: eventSource.readyState,
      url: eventSource.url,
      withCredentials: eventSource.withCredentials,
      timestamp: debugTimestamp()
    });

    eventSource.addEventListener('connected', () => {
      logger.debug('[MSG-DEBUG] SSE: Connection OPENED (connected event)', {
        readyState: eventSource.readyState,
        timestamp: debugTimestamp()
      });
      logger.info('[SSE] Connected to user inbox stream');
      setIsConnected(true);
      setConnectionError(null);
      resetHeartbeat();
    });

    eventSource.addEventListener('keep-alive', () => {
      logger.debug('[MSG-DEBUG] SSE: Keep-alive received', { timestamp: debugTimestamp() });
      resetHeartbeat();
    });

    eventSource.addEventListener('heartbeat', () => {
      logger.debug('[MSG-DEBUG] SSE: Heartbeat received', { timestamp: debugTimestamp() });
      resetHeartbeat();
    });

    // Handle all event types
    eventSource.addEventListener('new_message', (event) => {
      resetHeartbeat();
      try {
        const rawData = (event as MessageEvent).data;
        logger.debug('[MSG-DEBUG] SSE: new_message event received', {
          rawDataPreview: typeof rawData === 'string' ? rawData.substring(0, 200) : rawData,
          timestamp: debugTimestamp()
        });
        const parsed = JSON.parse(rawData);
        const data: SSEEvent = { ...parsed, type: 'new_message' };
        logger.debug('[MSG-DEBUG] SSE: new_message parsed', {
          type: data.type,
          conversationId: data.conversation_id,
          messageId: (data as { message?: { id?: string } }).message?.id,
          isMine: (data as { is_mine?: boolean }).is_mine,
          timestamp: debugTimestamp()
        });
        routeEvent(data);
      } catch (err) {
        logger.error('[MSG-DEBUG] SSE: Failed to parse new_message', { err, timestamp: debugTimestamp() });
      }
    });

    eventSource.addEventListener('typing_status', (event) => {
      try {
        const parsed = JSON.parse((event as MessageEvent).data);
        const data: SSEEvent = { ...parsed, type: 'typing_status' };
        logger.debug('[MSG-DEBUG] SSE: typing_status event', {
          conversationId: data.conversation_id,
          userId: (data as { user_id?: string }).user_id,
          timestamp: debugTimestamp()
        });
        routeEvent(data);
      } catch (err) {
        logger.error('[MSG-DEBUG] SSE: Failed to parse typing_status', { err, timestamp: debugTimestamp() });
      }
    });

    eventSource.addEventListener('read_receipt', (event) => {
      try {
        const parsed = JSON.parse((event as MessageEvent).data);
        const data: SSEEvent = { ...parsed, type: 'read_receipt' };
        logger.debug('[MSG-DEBUG] SSE: read_receipt event', {
          conversationId: data.conversation_id,
          messageIds: (data as { message_ids?: string[] }).message_ids,
          timestamp: debugTimestamp()
        });
        routeEvent(data);
      } catch (err) {
        logger.error('[MSG-DEBUG] SSE: Failed to parse read_receipt', { err, timestamp: debugTimestamp() });
      }
    });

    eventSource.addEventListener('reaction_update', (event) => {
      try {
        const parsed = JSON.parse((event as MessageEvent).data);
        const data: SSEEvent = { ...parsed, type: 'reaction_update' };
        logger.debug('[MSG-DEBUG] SSE: reaction_update event', {
          conversationId: data.conversation_id,
          messageId: (data as { message_id?: string }).message_id,
          emoji: (data as { emoji?: string }).emoji,
          action: (data as { action?: string }).action,
          timestamp: debugTimestamp()
        });
        routeEvent(data);
      } catch (err) {
        logger.error('[MSG-DEBUG] SSE: Failed to parse reaction_update', { err, timestamp: debugTimestamp() });
      }
    });

    eventSource.addEventListener('message_edited', (event) => {
      resetHeartbeat();
      try {
        const parsed = JSON.parse((event as MessageEvent).data);
        const data: SSEEvent = { ...parsed, type: 'message_edited' };
        const editData = data as SSEMessageEditedEvent;
        logger.debug('[MSG-DEBUG] SSE: message_edited event', {
          conversationId: data.conversation_id,
          messageId: editData.message_id,
          newContent: editData.data?.content,
          hasContent: !!editData.data?.content,
          timestamp: debugTimestamp()
        });
        routeEvent(data);
      } catch (err) {
        logger.error('[MSG-DEBUG] SSE: Failed to parse message_edited', { err, timestamp: debugTimestamp() });
      }
    });

    eventSource.addEventListener('message_deleted', (event) => {
      resetHeartbeat();
      try {
        const parsed = JSON.parse((event as MessageEvent).data);
        const data: SSEMessageDeletedEvent = { ...parsed, type: 'message_deleted' };
        logger.debug('[MSG-DEBUG] SSE: message_deleted event', {
          conversationId: data.conversation_id,
          messageId: data.message_id,
          timestamp: debugTimestamp(),
        });
        routeEvent(data);
      } catch (err) {
        logger.error('[MSG-DEBUG] SSE: Failed to parse message_deleted', { err, timestamp: debugTimestamp() });
      }
    });

    eventSource.onerror = (err) => {
      logger.error('[MSG-DEBUG] SSE: Connection ERROR', {
        readyState: eventSource.readyState,
        readyStateText: ['CONNECTING', 'OPEN', 'CLOSED'][eventSource.readyState] || 'UNKNOWN',
        error: err,
        timestamp: debugTimestamp()
      });
      setIsConnected(false);
      setConnectionError('Connection lost');
      eventSource.close();
      eventSourceRef.current = null;

      // Reconnect after delay
      logger.debug('[MSG-DEBUG] SSE: Will attempt reconnect in', { delayMs: RECONNECT_DELAY });
      reconnectTimeoutRef.current = setTimeout(() => {
        logger.debug('[MSG-DEBUG] SSE: Attempting reconnect...', { timestamp: debugTimestamp() });
        logger.info('[SSE] Attempting reconnect...');
        connect();
      }, RECONNECT_DELAY);
    };

    eventSourceRef.current = eventSource;
  }, [isAuthenticated, resetHeartbeat, routeEvent]);

  // Keep connectRef updated so heartbeat timeout can call it
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Connect on mount, cleanup on unmount
  useEffect(() => {
    logger.debug('[MSG-DEBUG] SSE useEffect running', {
      isAuthenticated,
      hasUser: !!user,
      userId: user?.id,
      timestamp: debugTimestamp(),
    });

    if (!isAuthenticated || !user) {
      logger.debug('[MSG-DEBUG] SSE useEffect: early return (not authenticated or no user)', {
        isAuthenticated,
        hasUser: !!user,
        timestamp: debugTimestamp(),
      });
      return;
    }

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
