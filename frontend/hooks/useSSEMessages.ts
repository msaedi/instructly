// frontend/hooks/useSSEMessages.ts
/**
 * Custom hook for managing Server-Sent Events (SSE) connections
 * for real-time messaging.
 *
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Connection status tracking
 * - Message processing and state management
 * - Browser notifications (if permitted)
 * - Notification sounds
 * - Proper cleanup on unmount
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { logger } from '@/lib/logger';
import type { MessageResponse } from '@/src/api/generated/instructly.schemas';
import { withApiBase } from '@/lib/apiBase';

// Connection states
export enum ConnectionStatus {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  ERROR = 'error',
  RECONNECTING = 'reconnecting',
}

// Hook options
interface UseSSEMessagesOptions {
  bookingId: string;
  enabled?: boolean;
  onMessage?: (message: MessageResponse) => void;
  onConnectionChange?: (status: ConnectionStatus) => void;
  playSound?: boolean;
  showNotifications?: boolean;
  maxReconnectAttempts?: number;
  reconnectDelay?: number;
}

// Hook return type
interface UseSSEMessagesReturn {
  messages: MessageResponse[];
  connectionStatus: ConnectionStatus;
  reconnect: () => void;
  disconnect: () => void;
  clearMessages: () => void;
  readReceipts: Record<string, Array<{ user_id: string; read_at: string }>>;
  typingStatus: { userId: string; userName: string; until: number } | null;
  reactionDeltas: Record<string, Record<string, number>>;
}

/**
 * Custom hook for real-time message streaming via SSE
 */
export function useSSEMessages({
  bookingId,
  enabled = true,
  onMessage,
  onConnectionChange,
  playSound = true,
  showNotifications = true,
  maxReconnectAttempts: _maxReconnectAttempts = 5,
  reconnectDelay: _reconnectDelay = 1000,
}: UseSSEMessagesOptions): UseSSEMessagesReturn {
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [readReceipts, setReadReceipts] = useState<Record<string, Array<{ user_id: string; read_at: string }>>>({});
  const [typingStatus, setTypingStatus] = useState<{ userId: string; userName: string; until: number } | null>(null);
  const [reactionDeltas, setReactionDeltas] = useState<Record<string, Record<string, number>>>({});
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(
    ConnectionStatus.DISCONNECTED
  );

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isUnmountingRef = useRef(false);
  const lastErrorTimeRef = useRef<number>(0);
  const reconnectDelayRef = useRef(1000); // Start with 1 second
  const authFailureRef = useRef(false);
  const onMessageRef = useRef(onMessage);
  const onConnectionChangeRef = useRef(onConnectionChange);
  // Refs to store latest connect/disconnect functions - avoids effect dependency issues
  const connectRef = useRef<() => void>(() => {});
  const disconnectRef = useRef<() => void>(() => {});

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    onConnectionChangeRef.current = onConnectionChange;
  }, [onConnectionChange]);

  // Auto-clear typing indicator when it expires
  useEffect(() => {
    if (!typingStatus) return;

    const now = Date.now();
    const remainingMs = typingStatus.until - now;

    if (remainingMs <= 0) {
      // Already expired, clear immediately
      setTypingStatus(null);
      return;
    }

    // Set timeout to clear when it expires
    const timeout = setTimeout(() => {
      setTypingStatus(null);
    }, remainingMs);

    return () => clearTimeout(timeout);
  }, [typingStatus]);

  // Update connection status and notify listener
  const updateConnectionStatus = useCallback((status: ConnectionStatus) => {
    setConnectionStatus(status);
    onConnectionChangeRef.current?.(status);
  }, []);

  // Play notification sound
  const playNotificationSound = useCallback(() => {
    if (!playSound) return;

    try {
      // Create a simple beep sound using Web Audio API
      const audioContext = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);

      oscillator.frequency.value = 800; // Frequency in Hz
      oscillator.type = 'sine';

      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);

      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.2);
    } catch {
    }
  }, [playSound]);

  // Show browser notification
  const showBrowserNotification = useCallback((message: MessageResponse) => {
    if (!showNotifications || !('Notification' in window)) return;

    // Request permission if not granted
    if (Notification.permission === 'default') {
      void Notification.requestPermission();
      return;
    }

    if (Notification.permission !== 'granted') return;

    try {
      const notification = new Notification('New Message', {
        body: message.content,
        icon: '/favicon.ico',
        tag: `message-${message.id}`,
        requireInteraction: false,
      });

      // Auto-close after 5 seconds
      setTimeout(() => notification.close(), 5000);

      // Focus window on click
      notification.onclick = () => {
        window.focus();
        notification.close();
      };
    } catch {
    }
  }, [showNotifications]);

  // Process incoming message
  const processMessage = useCallback((messageData: unknown) => {
    logger.info('[SSE] processMessage called', { messageData });
    try {
      // Type guard for message data
      if (!messageData || typeof messageData !== 'object') {
        logger.warn('Invalid message data received');
        return;
      }

      const data = messageData as Record<string, unknown>;
      const eventType = data['type'] || 'message';

      if (eventType === 'read_receipt') {
        const { message_id, user_id, read_at } = data;
        if (typeof message_id === 'string' && typeof user_id === 'string' && typeof read_at === 'string') {
          setReadReceipts(prev => ({
            ...prev,
            [message_id]: [...(prev[message_id] || []), { user_id, read_at }],
          }));
        }
        return;
      }

      if (eventType === 'typing_status') {
        const { user_id, user_name } = data;
        logger.debug('[SSE] typing_status event received:', { user_id, user_name, data });
        if (typeof user_id === 'string' && typeof user_name === 'string') {
          // Clear after 3 seconds
          setTypingStatus({ userId: user_id, userName: user_name, until: Date.now() + 3000 });
          logger.debug('[SSE] typingStatus set:', { userId: user_id, userName: user_name });
        }
        return;
      }

      if (eventType === 'reaction_update') {
        const { message_id, emoji, action } = data;
        if (typeof message_id === 'string' && typeof emoji === 'string' && (action === 'added' || action === 'removed')) {
          setReactionDeltas(prev => {
            const current = prev[message_id] || {};
            const delta = action === 'added' ? 1 : -1;
            const nextCount = (current[emoji] || 0) + delta;
            return {
              ...prev,
              [message_id]: { ...current, [emoji]: nextCount },
            };
          });
        }
        return;
      }

      const message: MessageResponse = {
        ...data,
        created_at: (data['created_at'] as string) || new Date().toISOString(),
        updated_at: (data['updated_at'] as string) || new Date().toISOString(),
      } as MessageResponse;

      // Add to state
      setMessages(prev => [...prev, message]);

      // Notify listeners
      onMessageRef.current?.(message);

      // Play sound and show notification
      playNotificationSound();
      showBrowserNotification(message);

    } catch {
      logger.error('Error processing message');
    }
  }, [playNotificationSound, showBrowserNotification]);

  const verifyAuthStatus = useCallback(async () => {
    try {
      const response = await fetch(withApiBase('/api/v1/auth/me'), {
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });
      if (response.status === 401 || response.status === 403) {
        return false;
      }
    } catch {
      // Treat network errors as transient; allow reconnect logic to handle them
      return true;
    }
    return true;
  }, []);

  const evaluateAuthFailure = useCallback(async () => {
    const stillValid = await verifyAuthStatus();
    if (!stillValid) {
      if (!authFailureRef.current) {
        logger.warn('SSE authentication failed; halting reconnect attempts until session is refreshed');
      }
      authFailureRef.current = true;
      updateConnectionStatus(ConnectionStatus.ERROR);
      return true;
    }
    return false;
  }, [updateConnectionStatus, verifyAuthStatus]);

  // Connect to SSE endpoint
  const connect = useCallback(() => {
    logger.info('[SSE] connect() called', { enabled, bookingId, authFailure: authFailureRef.current });
    if (!enabled || !bookingId || isUnmountingRef.current || authFailureRef.current) {
      logger.info('[SSE] Connection skipped', { enabled, bookingId, isUnmounting: isUnmountingRef.current, authFailure: authFailureRef.current });
      return;
    }

    // Check if already connected or connecting
    if (eventSourceRef.current) {
      const state = eventSourceRef.current.readyState;
      if (state === EventSource.OPEN || state === EventSource.CONNECTING) {
        return;
      }
      // Close any existing connection that's not open or connecting
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    updateConnectionStatus(ConnectionStatus.CONNECTING);

    try {
      // Cookie-based session: connect without localStorage token
      // Phase 10: Migrated to v1 messages endpoint
      const url = withApiBase(`/api/v1/messages/stream/${bookingId}`);

      const eventSource = new EventSource(url, { withCredentials: true } as EventSourceInit);
      eventSourceRef.current = eventSource;

      // Connection opened
      eventSource.onopen = () => {
        logger.info('SSE connection established', { bookingId });
        updateConnectionStatus(ConnectionStatus.CONNECTED);
        reconnectAttemptsRef.current = 0;
        reconnectDelayRef.current = 1000; // Reset delay on successful connection
      };


      // Handle messages
      eventSource.addEventListener('message', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch {
          logger.error('Error parsing SSE message');
        }
      });

      // Read receipt events
      eventSource.addEventListener('read_receipt', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch {
          logger.error('Error parsing read_receipt');
        }
      });

      // Typing indicator events
      eventSource.addEventListener('typing_status', (event) => {
        try {
          logger.debug('[SSE] Raw typing_status event received');
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch {
          logger.error('Error parsing typing_status');
        }
      });

      // Reaction updates
      eventSource.addEventListener('reaction_update', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch {
          logger.error('Error parsing reaction_update');
        }
      });

      // Handle connection event
      eventSource.addEventListener('connected', () => {
      });

      // Handle heartbeat
      eventSource.addEventListener('heartbeat', () => {
      });

      // Handle keep-alive
      eventSource.addEventListener('keep-alive', () => {
      });

      // Handle errors with throttling
      eventSource.onerror = (error) => {
        void (async () => {
          logger.error('SSE connection error', {
            bookingId,
            readyState: eventSource.readyState,
            error: error
          });
          updateConnectionStatus(ConnectionStatus.ERROR);

          eventSource.close();
          if (eventSourceRef.current === eventSource) {
            eventSourceRef.current = null;
          }

          const haltForAuth = await evaluateAuthFailure();
          if (haltForAuth || isUnmountingRef.current) {
            return;
          }

          // Check if last error was too recent (within 1 second)
          const now = Date.now();
          const timeSinceLastError = now - lastErrorTimeRef.current;
          lastErrorTimeRef.current = now;

          if (timeSinceLastError < 1000) {
            logger.warn('Rapid reconnection detected, increasing delay');
            reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 30000); // Max 30 seconds
          }

          if (reconnectAttemptsRef.current >= 10) {
            logger.warn('Max reconnection attempts reached (10)');
            updateConnectionStatus(ConnectionStatus.DISCONNECTED);
            reconnectDelayRef.current = 1000;
            return;
          }

          reconnectAttemptsRef.current += 1;

          const baseDelay = reconnectDelayRef.current;
          const delay = Math.min(baseDelay * Math.pow(2, Math.min(reconnectAttemptsRef.current - 1, 4)), 30000);

          logger.info(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/10)`);
          updateConnectionStatus(ConnectionStatus.RECONNECTING);

          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        })();
      };

    } catch {
      logger.error('Failed to create SSE connection');
      updateConnectionStatus(ConnectionStatus.ERROR);
    }
  }, [
    enabled,
    bookingId,
    updateConnectionStatus,
    processMessage,
    evaluateAuthFailure,
  ]);

  // Disconnect from SSE
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      logger.info('SSE connection closed', { bookingId });
    }

    updateConnectionStatus(ConnectionStatus.DISCONNECTED);
    reconnectAttemptsRef.current = 0;
  }, [bookingId, updateConnectionStatus]);

  // Keep refs updated with latest functions
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    disconnectRef.current = disconnect;
  }, [disconnect]);

  // Manual reconnect
  const reconnect = useCallback(() => {
    authFailureRef.current = false;
    disconnect();
    reconnectAttemptsRef.current = 0;
    reconnectDelayRef.current = 1000; // Reset delay for manual reconnect
    connect();
  }, [connect, disconnect]);

  // Clear messages
  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  // Setup and cleanup
  // Using refs for connect/disconnect to avoid effect re-running when functions change
  useEffect(() => {
    if (!enabled || !bookingId) {
      isUnmountingRef.current = true;
      disconnectRef.current();
      return () => {};
    }

    isUnmountingRef.current = false;
    // Clear messages when switching bookings
    setMessages([]);
    setReadReceipts({});
    setTypingStatus(null);
    setReactionDeltas({});

    const connectTimeout = setTimeout(() => {
      if (!isUnmountingRef.current) {
        connectRef.current();
      }
    }, 100);

    return () => {
      isUnmountingRef.current = true;
      clearTimeout(connectTimeout);
      disconnectRef.current();
    };
  }, [enabled, bookingId]);

  // Auto-clear typing status when expired
  useEffect(() => {
    if (!typingStatus) return;
    const now = Date.now();
    const ms = Math.max(0, typingStatus.until - now);
    const t = setTimeout(() => setTypingStatus(null), ms || 3000);
    return () => clearTimeout(t);
  }, [typingStatus]);

  return {
    messages,
    connectionStatus,
    reconnect,
    disconnect,
    clearMessages,
    readReceipts,
    typingStatus,
    reactionDeltas,
  };
}
