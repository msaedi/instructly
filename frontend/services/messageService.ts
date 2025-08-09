// frontend/services/messageService.ts
/**
 * Message Service for chat functionality
 *
 * Handles all API interactions for the real-time messaging system.
 * Following the service-first pattern established in the codebase.
 */

import { fetchWithAuth, API_URL } from '@/lib/api';
import { logger } from '@/lib/logger';

// Types
export interface Message {
  id: number;
  booking_id: number;
  sender_id: number;
  content: string;
  created_at: string;
  updated_at: string;
  is_deleted: boolean;
  delivered_at?: string | null;
  edited_at?: string | null;
  read_by?: Array<{ user_id: number; read_at: string }>;
  sender?: {
    id: number;
    full_name: string;
    email: string;
  };
}

export interface SendMessageRequest {
  booking_id: number;
  content: string;
}

export interface SendMessageResponse {
  success: boolean;
  message: Message;
}

export interface MessagesHistoryResponse {
  booking_id: number;
  messages: Message[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface UnreadCountResponse {
  unread_count: number;
  user_id: number;
}

export interface MarkMessagesReadRequest {
  booking_id?: number;
  message_ids?: number[];
}

/**
 * Message Service Class
 *
 * Provides methods for:
 * - Sending messages
 * - Fetching message history
 * - Managing unread counts
 * - Marking messages as read
 * - Deleting messages
 */
class MessageService {
  private readonly baseUrl = '/api/messages';

  /**
   * Send a message to a booking chat
   */
  async sendMessage(request: SendMessageRequest): Promise<SendMessageResponse> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const error = await response.json();
        logger.error('Send message error details', {
          status: response.status,
          error: error,
          detail: error.detail,
          body: request
        });
        throw new Error(error.detail || JSON.stringify(error) || 'Failed to send message');
      }

      const data = await response.json();
      logger.info('Message sent successfully', { booking_id: request.booking_id });
      return data;
    } catch (error) {
      logger.error('Failed to send message', error);
      throw error;
    }
  }

  /**
   * Get message history for a booking
   */
  async getMessageHistory(
    bookingId: number,
    limit: number = 50,
    offset: number = 0
  ): Promise<MessagesHistoryResponse> {
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      });

      const response = await fetchWithAuth(
        `${this.baseUrl}/history/${bookingId}?${params}`
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to fetch message history');
      }

      const data = await response.json();
      logger.debug('Message history fetched', {
        booking_id: bookingId,
        message_count: data.messages.length
      });
      return data;
    } catch (error) {
      logger.error('Failed to fetch message history', error);
      throw error;
    }
  }

  /**
   * Get total unread message count for current user
   */
  async getUnreadCount(): Promise<UnreadCountResponse> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/unread-count`);

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to fetch unread count');
      }

      const data = await response.json();
      logger.debug('Unread count fetched', { count: data.unread_count });
      return data;
    } catch (error) {
      logger.error('Failed to fetch unread count', error);
      throw error;
    }
  }

  /**
   * Mark messages as read
   */
  async markMessagesAsRead(request: MarkMessagesReadRequest): Promise<number> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/mark-read`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        // Best-effort: avoid noisy logs in UI if mark-read fails
        try {
          await response.json();
        } catch {}
        return 0;
      }

      const data = await response.json();
      return data.messages_marked;
    } catch (error) {
      // Swallow mark-read errors to avoid user-facing noise
      return 0;
    }
  }

  /**
   * Delete a message (soft delete)
   */
  async deleteMessage(messageId: number): Promise<boolean> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/${messageId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to delete message');
      }

      logger.info('Message deleted', { message_id: messageId });
      return true;
    } catch (error) {
      logger.error('Failed to delete message', error);
      throw error;
    }
  }

  /**
   * Send typing indicator (ephemeral)
   */
  async sendTyping(bookingId: number): Promise<void> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/typing/${bookingId}`, {
        method: 'POST',
      });
      // 204 expected; ignore body
      if (!response.ok) {
        // Silently ignore to avoid user-facing noise
        logger.debug('Typing indicator not accepted', { status: response.status });
      }
    } catch (error) {
      // Silent catch; typing is best-effort
    }
  }

  /**
   * Add a reaction to a message (optimistic-friendly)
   */
  async addReaction(messageId: number, emoji: string): Promise<boolean> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/${messageId}/reactions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ emoji }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Remove a reaction from a message (optimistic-friendly)
   */
  async removeReaction(messageId: number, emoji: string): Promise<boolean> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/${messageId}/reactions`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ emoji }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Edit an existing message (own message, 5-minute window)
   */
  async editMessage(messageId: number, content: string): Promise<boolean> {
    try {
      const response = await fetchWithAuth(`${this.baseUrl}/${messageId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Fetch backend-configured message settings
   */
  async getMessageConfig(): Promise<{ edit_window_minutes: number }> {
    const response = await fetchWithAuth(`${this.baseUrl}/config`);
    if (!response.ok) return { edit_window_minutes: 5 };
    return response.json();
  }

  /**
   * Create SSE connection for real-time messages
   *
   * Note: This returns an EventSource object that must be managed
   * by the calling component/hook for proper cleanup
   */
  createMessageStream(bookingId: number): EventSource {
    const token = localStorage.getItem('access_token');
    const url = `${API_URL}${this.baseUrl}/stream/${bookingId}`;

    // EventSource doesn't support custom headers, so we pass token as query param
    const urlWithAuth = `${url}?token=${encodeURIComponent(token || '')}`;

    logger.info('Creating SSE connection', { booking_id: bookingId });
    return new EventSource(urlWithAuth);
  }
}

// Export singleton instance
export const messageService = new MessageService();
