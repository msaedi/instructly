/**
 * Tests for instructor messages page - message fetching behavior
 * Ensures we don't spam /api/messages/history for zero-message conversations
 */

import { renderHook, waitFor } from '@testing-library/react';
import { useEffect, useState, useRef } from 'react';

// Mock the message service (Orval layer)
const mockFetchMessageHistory = jest.fn();
jest.mock('@/src/api/services/messages', () => ({
  fetchMessageHistory: (...args: unknown[]) => mockFetchMessageHistory(...args),
}));

// Simplified version of the fetch effect logic
type MessagesByThread = Record<string, Array<{ id: string }>>;

const useFetchMessagesEffect = (
  selectedChat: string | null,
  activeConversation: { primaryBookingId: string } | null,
  currentUserId: string | null
) => {
  const [messagesByThread, setMessagesByThread] = useState<MessagesByThread>({});
  const fetchingThreadsRef = useRef<Set<string>>(new Set());
  const loadedThreadsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!selectedChat || selectedChat === '__compose__') return;
    if (!activeConversation) return;

    // Skip if we've already loaded (or attempted to load) this conversation
    // Using ref instead of state to avoid dependency issues
    if (loadedThreadsRef.current.has(selectedChat)) return;

    // Skip if already fetching this thread
    if (fetchingThreadsRef.current.has(selectedChat)) return;

    const fetchMessages = async () => {
      const bookingId = activeConversation.primaryBookingId;
      if (!bookingId || !currentUserId) return;

      fetchingThreadsRef.current.add(selectedChat);

      try {
        const history = await mockFetchMessageHistory(bookingId);
        const messages = history.messages || [];

        setMessagesByThread((prev) => ({
          ...prev,
          [selectedChat]: messages,
        }));

        // Mark as loaded even if empty
        loadedThreadsRef.current.add(selectedChat);
      } catch {
        // On error, don't mark as loaded
      } finally {
        fetchingThreadsRef.current.delete(selectedChat);
      }
    };

    void fetchMessages();
    // Note: messagesByThread removed from dependencies to prevent infinite loop
  }, [selectedChat, activeConversation, currentUserId]);

  return { messagesByThread, fetchCallCount: mockFetchMessageHistory.mock.calls.length };
};

describe('Instructor Messages - Message Fetching', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches messages exactly once for zero-message conversations', async () => {
    // Mock zero-message response
    mockFetchMessageHistory.mockResolvedValue({
      messages: [],
      limit: 50,
      offset: 0,
      has_more: false,
    });

    const { result, rerender } = renderHook(
      ({ selectedChat, activeConversation, currentUserId }) =>
        useFetchMessagesEffect(selectedChat, activeConversation, currentUserId),
      {
        initialProps: {
          selectedChat: 'student-john',
          activeConversation: { primaryBookingId: 'booking-john-123' },
          currentUserId: 'instructor-1',
        },
      }
    );

    // Wait for the fetch to complete
    await waitFor(() => {
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
    });

    expect(mockFetchMessageHistory).toHaveBeenCalledWith('booking-john-123');

    // Verify empty array was stored
    await waitFor(() => {
      expect(result.current.messagesByThread['student-john']).toEqual([]);
    });

    // Force multiple re-renders to simulate React updates
    for (let i = 0; i < 5; i++) {
      rerender({
        selectedChat: 'student-john',
        activeConversation: { primaryBookingId: 'booking-john-123' },
        currentUserId: 'instructor-1',
      });
    }

    // Should still be called only once
    await waitFor(() => {
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
    });
  });

  it('fetches messages exactly once for conversations with messages', async () => {
    // Mock response with messages
    const mockMessages = [{ id: 'msg-1' }];

    mockFetchMessageHistory.mockResolvedValue({
      messages: mockMessages,
      limit: 50,
      offset: 0,
      has_more: false,
    });

    const { result, rerender } = renderHook(
      ({ selectedChat, activeConversation, currentUserId }) =>
        useFetchMessagesEffect(selectedChat, activeConversation, currentUserId),
      {
        initialProps: {
          selectedChat: 'student-emma',
          activeConversation: { primaryBookingId: 'booking-emma-456' },
          currentUserId: 'instructor-1',
        },
      }
    );

    // Wait for the fetch to complete
    await waitFor(() => {
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
    });

    expect(mockFetchMessageHistory).toHaveBeenCalledWith('booking-emma-456');

    // Verify messages were stored
    await waitFor(() => {
      expect(result.current.messagesByThread['student-emma']).toEqual(mockMessages);
    });

    // Force multiple re-renders
    for (let i = 0; i < 5; i++) {
      rerender({
        selectedChat: 'student-emma',
        activeConversation: { primaryBookingId: 'booking-emma-456' },
        currentUserId: 'instructor-1',
      });
    }

    // Should still be called only once
    await waitFor(() => {
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
    });
  });

  it('prevents duplicate simultaneous fetches for the same conversation', async () => {
    // Mock slow API response
    mockFetchMessageHistory.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(
            () =>
              resolve({
                messages: [],
                limit: 50,
                offset: 0,
                has_more: false,
              }),
            100
          );
        })
    );

    const { rerender } = renderHook(
      ({ selectedChat, activeConversation, currentUserId }) =>
        useFetchMessagesEffect(selectedChat, activeConversation, currentUserId),
      {
        initialProps: {
          selectedChat: 'student-slow',
          activeConversation: { primaryBookingId: 'booking-slow-789' },
          currentUserId: 'instructor-1',
        },
      }
    );

    // Trigger multiple rapid re-renders before first fetch completes
    for (let i = 0; i < 3; i++) {
      rerender({
        selectedChat: 'student-slow',
        activeConversation: { primaryBookingId: 'booking-slow-789' },
        currentUserId: 'instructor-1',
      });
    }

    // Wait for all to settle
    await waitFor(
      () => {
        expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
      },
      { timeout: 500 }
    );

    // Even with rapid re-renders, should only fetch once
    expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
  });

  it('allows retry on fetch error', async () => {
    // First call fails
    mockFetchMessageHistory.mockRejectedValueOnce(new Error('Network error'));

    const { rerender } = renderHook(
      ({ selectedChat, activeConversation, currentUserId }) =>
        useFetchMessagesEffect(selectedChat, activeConversation, currentUserId),
      {
        initialProps: {
          selectedChat: 'student-error',
          activeConversation: { primaryBookingId: 'booking-error-999' },
          currentUserId: 'instructor-1',
        },
      }
    );

    // Wait for first call to fail
    await waitFor(() => {
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(1);
    });

    // Mock successful response for retry
    mockFetchMessageHistory.mockResolvedValueOnce({
      messages: [],
      limit: 50,
      offset: 0,
      has_more: false,
    });

    // Deselect and reselect to trigger retry
    rerender({
      selectedChat: null as unknown as string,
      activeConversation: null as unknown as { primaryBookingId: string },
      currentUserId: 'instructor-1',
    });

    rerender({
      selectedChat: 'student-error',
      activeConversation: { primaryBookingId: 'booking-error-999' },
      currentUserId: 'instructor-1',
    });

    // Should retry on next selection
    await waitFor(() => {
      expect(mockFetchMessageHistory).toHaveBeenCalledTimes(2);
    });
  });
});
