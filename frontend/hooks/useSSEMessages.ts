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
import { Message } from '@/services/messageService';

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
  onMessage?: (message: Message) => void;
  onConnectionChange?: (status: ConnectionStatus) => void;
  playSound?: boolean;
  showNotifications?: boolean;
  maxReconnectAttempts?: number;
  reconnectDelay?: number;
}

// Hook return type
interface UseSSEMessagesReturn {
  messages: Message[];
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
  const [messages, setMessages] = useState<Message[]>([]);
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

  // Update connection status and notify listener
  const updateConnectionStatus = useCallback((status: ConnectionStatus) => {
    setConnectionStatus(status);
    onConnectionChange?.(status);
  }, [onConnectionChange]);

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
    } catch (_error) {
    }
  }, [playSound]);

  // Show browser notification
  const showBrowserNotification = useCallback((message: Message) => {
    if (!showNotifications || !('Notification' in window)) return;

    // Request permission if not granted
    if (Notification.permission === 'default') {
      Notification.requestPermission();
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
    } catch (_error) {
    }
  }, [showNotifications]);

  // Process incoming message
  const processMessage = useCallback((messageData: unknown) => {
    try {
      // Type guard for message data
      if (!messageData || typeof messageData !== 'object') {
        logger.warn('Invalid message data received');
        return;
      }

      const data = messageData as Record<string, unknown>;
      const eventType = data.type || 'message';

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
        if (typeof user_id === 'string' && typeof user_name === 'string') {
          // Clear after 3 seconds
          setTypingStatus({ userId: user_id, userName: user_name, until: Date.now() + 3000 });
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

      const message: Message = {
        ...data,
        created_at: (data.created_at as string) || new Date().toISOString(),
        updated_at: (data.updated_at as string) || new Date().toISOString(),
      } as Message;

      // Add to state
      setMessages(prev => [...prev, message]);

      // Notify listeners
      onMessage?.(message);

      // Play sound and show notification
      playNotificationSound();
      showBrowserNotification(message);

    } catch (_error) {
      logger.error('Error processing message');
    }
  }, [onMessage, playNotificationSound, showBrowserNotification]);

  // Connect to SSE endpoint
  const connect = useCallback(() => {
    if (!enabled || isUnmountingRef.current) return;

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
      const token = localStorage.getItem('access_token');
      if (!token) {
        logger.warn('No auth token available for SSE connection');
        updateConnectionStatus(ConnectionStatus.ERROR);
        return;
      }

      // Create EventSource with auth token in URL as query parameter
      const apiUrl = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
      const url = `${apiUrl}/api/messages/stream/${bookingId}?token=${encodeURIComponent(token)}`;

      // Don't use withCredentials when token is in URL - can cause browser issues
      const eventSource = new EventSource(url);
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
        } catch (_error) {
          logger.error('Error parsing SSE message');
        }
      });

      // Read receipt events
      eventSource.addEventListener('read_receipt', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch (_error) {
          logger.error('Error parsing read_receipt');
        }
      });

      // Typing indicator events
      eventSource.addEventListener('typing_status', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch (_error) {
          logger.error('Error parsing typing_status');
        }
      });

      // Reaction updates
      eventSource.addEventListener('reaction_update', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch (_error) {
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
        logger.error('SSE connection error', {
          bookingId,
          readyState: eventSource.readyState,
          error: error
        });
        updateConnectionStatus(ConnectionStatus.ERROR);

        // Close the connection
        eventSource.close();
        eventSourceRef.current = null;

        // Check if last error was too recent (within 1 second)
        const now = Date.now();
        const timeSinceLastError = now - lastErrorTimeRef.current;
        lastErrorTimeRef.current = now;

        if (timeSinceLastError < 1000) {
          logger.warn('Rapid reconnection detected, increasing delay');
          // Double the delay if we're reconnecting too quickly
          reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 30000); // Max 30 seconds
        }

        // Attempt reconnection if not unmounting and within attempt limit
        if (!isUnmountingRef.current && reconnectAttemptsRef.current < 10) { // Increased to 10 attempts
          reconnectAttemptsRef.current++;

          // Use exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
          const baseDelay = reconnectDelayRef.current;
          const delay = Math.min(baseDelay * Math.pow(2, Math.min(reconnectAttemptsRef.current - 1, 4)), 30000);

          logger.info(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/10)`);
          updateConnectionStatus(ConnectionStatus.RECONNECTING);

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else if (reconnectAttemptsRef.current >= 10) {
          logger.warn('Max reconnection attempts reached (10)');
          updateConnectionStatus(ConnectionStatus.DISCONNECTED);
          // Reset delay for next manual reconnection
          reconnectDelayRef.current = 1000;
        }
      };

    } catch (_error) {
      logger.error('Failed to create SSE connection');
      updateConnectionStatus(ConnectionStatus.ERROR);
    }
  }, [
    enabled,
    bookingId,
    updateConnectionStatus,
    processMessage,
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

  // Manual reconnect
  const reconnect = useCallback(() => {
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
  useEffect(() => {
    isUnmountingRef.current = false;
    let localEventSource: EventSource | null = null;
    let connectTimeout: NodeJS.Timeout | null = null;

    if (!enabled) return;

    // Connection logic
    const establishConnection = () => {
      // Check if already connected
      if (localEventSource && (localEventSource.readyState === EventSource.OPEN || localEventSource.readyState === EventSource.CONNECTING)) {
        return;
      }

      const token = localStorage.getItem('access_token');
      if (!token) {
        logger.warn('No auth token available for SSE connection');
        updateConnectionStatus(ConnectionStatus.ERROR);
        return;
      }

      updateConnectionStatus(ConnectionStatus.CONNECTING);

      const apiUrl = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
      const url = `${apiUrl}/api/messages/stream/${bookingId}?token=${encodeURIComponent(token)}`;

      // Create new EventSource
      localEventSource = new EventSource(url);
      eventSourceRef.current = localEventSource;

      localEventSource.onopen = () => {
        logger.info('SSE connection established', { bookingId });
        updateConnectionStatus(ConnectionStatus.CONNECTED);
        reconnectAttemptsRef.current = 0;
        reconnectDelayRef.current = 1000;
      };

      localEventSource.addEventListener('connected', (_event) => {
      });

      localEventSource.addEventListener('message', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch (_error) {
          logger.error('Error parsing SSE message');
        }
      });

      localEventSource.addEventListener('read_receipt', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch (_error) {
          logger.error('Error parsing read_receipt');
        }
      });

      localEventSource.addEventListener('typing_status', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch (_error) {
          logger.error('Error parsing typing_status');
        }
      });

      localEventSource.addEventListener('reaction_update', (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data);
          processMessage(data);
        } catch (_error) {
          logger.error('Error parsing reaction_update');
        }
      });

      localEventSource.addEventListener('heartbeat', () => {
      });

      localEventSource.addEventListener('keep-alive', () => {
      });

      localEventSource.onerror = (error) => {
        logger.error('SSE connection error', { bookingId, error });
        updateConnectionStatus(ConnectionStatus.ERROR);

        if (localEventSource) {
          localEventSource.close();
        }

        // Don't reconnect on unmount
        if (!isUnmountingRef.current) {
          updateConnectionStatus(ConnectionStatus.DISCONNECTED);
        }
      };
    };

    // Add a small delay to prevent rapid connect/disconnect on mount
    connectTimeout = setTimeout(() => {
      if (!isUnmountingRef.current && enabled) {
        establishConnection();
      }
    }, 100);

    return () => {
      isUnmountingRef.current = true;

      if (connectTimeout) {
        clearTimeout(connectTimeout);
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      // Close connection
      if (localEventSource) {
        localEventSource.close();
        logger.info('SSE connection closed on unmount', { bookingId });
      }

      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      updateConnectionStatus(ConnectionStatus.DISCONNECTED);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, bookingId]); // Only re-run when enabled or bookingId changes

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
