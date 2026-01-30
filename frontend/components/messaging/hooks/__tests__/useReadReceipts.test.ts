/**
 * @jest-environment jsdom
 */
import { renderHook } from '@testing-library/react';
import {
  useReadReceipts,
  type ReadReceiptEntry,
  type ReadReceiptMap,
  type ReadReceiptMessage,
} from '../useReadReceipts';

// Test message interface
interface TestMessage extends ReadReceiptMessage {
  id: string;
  sender_id: string;
  read_by: ReadReceiptEntry[] | null;
  created_at: string;
}

// Helper to create test messages
function createTestMessage(overrides: Partial<TestMessage> = {}): TestMessage {
  return {
    id: 'msg-1',
    sender_id: 'user-sender',
    read_by: null,
    created_at: '2024-01-15T10:00:00Z',
    ...overrides,
  };
}

describe('useReadReceipts', () => {
  const currentUserId = 'user-current';

  // Standard accessor functions
  const getReadBy = (m: TestMessage) => m.read_by;
  const isOwnMessage = (m: TestMessage) => m.sender_id === currentUserId;
  const getCreatedAt = (m: TestMessage) =>
    m.created_at ? new Date(m.created_at) : null;

  describe('mergedReadReceipts', () => {
    it('merges SSE receipts with message read_by', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
        }),
      ];

      const sseReadReceipts: ReadReceiptMap = {
        'msg-1': [{ user_id: 'user-b', read_at: '2024-01-15T10:02:00Z' }],
      };

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts,
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      // Should contain both user-a (from message) and user-b (from SSE)
      expect(result.current.mergedReadReceipts['msg-1']).toHaveLength(2);
      expect(result.current.mergedReadReceipts['msg-1']).toContainEqual({
        user_id: 'user-a',
        read_at: '2024-01-15T10:01:00Z',
      });
      expect(result.current.mergedReadReceipts['msg-1']).toContainEqual({
        user_id: 'user-b',
        read_at: '2024-01-15T10:02:00Z',
      });
    });

    it('deduplicates receipts with same user_id and read_at (line 107)', () => {
      const duplicateReceipt = {
        user_id: 'user-a',
        read_at: '2024-01-15T10:01:00Z',
      };

      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          read_by: [duplicateReceipt],
        }),
      ];

      // SSE contains the same receipt
      const sseReadReceipts: ReadReceiptMap = {
        'msg-1': [duplicateReceipt],
      };

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts,
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      // Should only have one entry, not two
      expect(result.current.mergedReadReceipts['msg-1']).toHaveLength(1);
    });

    it('handles messages with null read_by', () => {
      const messages: TestMessage[] = [
        createTestMessage({ id: 'msg-1', read_by: null }),
      ];

      const sseReadReceipts: ReadReceiptMap = {};

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts,
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      // Message with null read_by should not appear in map
      expect(result.current.mergedReadReceipts['msg-1']).toBeUndefined();
    });

    it('handles empty messages array', () => {
      const { result } = renderHook(() =>
        useReadReceipts({
          messages: [],
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.mergedReadReceipts).toEqual({});
      expect(result.current.lastReadMessageId).toBeNull();
    });

    it('skips receipts with missing required fields', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          read_by: [
            { user_id: '', read_at: '2024-01-15T10:01:00Z' }, // Missing user_id
            { user_id: 'user-a', read_at: '' }, // Missing read_at
            { user_id: 'user-b', read_at: '2024-01-15T10:02:00Z' }, // Valid
          ],
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      // Only the valid receipt should be included
      expect(result.current.mergedReadReceipts['msg-1']).toHaveLength(1);
      expect(result.current.mergedReadReceipts['msg-1']?.[0]?.user_id).toBe('user-b');
    });
  });

  describe('lastReadMessageId', () => {
    it('finds the most recent own message with read receipts', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          sender_id: currentUserId,
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
          created_at: '2024-01-15T10:00:00Z',
        }),
        createTestMessage({
          id: 'msg-2',
          sender_id: currentUserId,
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T11:01:00Z' }],
          created_at: '2024-01-15T11:00:00Z', // More recent
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.lastReadMessageId).toBe('msg-2');
    });

    it('returns null when no own messages have read receipts', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          sender_id: currentUserId,
          read_by: null, // No receipts
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.lastReadMessageId).toBeNull();
    });

    it('returns null when currentUserId is empty', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          sender_id: 'some-user',
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId: '', // Empty
          getReadBy,
          isOwnMessage: () => false,
          getCreatedAt,
        })
      );

      expect(result.current.lastReadMessageId).toBeNull();
    });

    it('skips messages without valid created_at timestamp', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          sender_id: currentUserId,
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
          created_at: 'invalid-date',
        }),
        createTestMessage({
          id: 'msg-2',
          sender_id: currentUserId,
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T11:01:00Z' }],
          created_at: '2024-01-15T11:00:00Z', // Valid
        }),
      ];

      const getCreatedAtWithInvalid = (m: TestMessage) => {
        const d = new Date(m.created_at);
        return Number.isNaN(d.getTime()) ? null : d;
      };

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt: getCreatedAtWithInvalid,
        })
      );

      expect(result.current.lastReadMessageId).toBe('msg-2');
    });

    it('only considers own messages', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          sender_id: 'other-user',
          read_by: [{ user_id: currentUserId, read_at: '2024-01-15T10:01:00Z' }],
          created_at: '2024-01-15T10:00:00Z',
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      // Message from other user should not be lastReadMessageId
      expect(result.current.lastReadMessageId).toBeNull();
    });
  });

  describe('isMessageRead helper (lines 156-157)', () => {
    it('returns true for messages with read receipts', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.isMessageRead('msg-1')).toBe(true);
    });

    it('returns false for messages without read receipts', () => {
      const messages: TestMessage[] = [
        createTestMessage({ id: 'msg-1', read_by: null }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.isMessageRead('msg-1')).toBe(false);
    });

    it('returns false for unknown message IDs', () => {
      const { result } = renderHook(() =>
        useReadReceipts({
          messages: [],
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.isMessageRead('unknown-msg')).toBe(false);
    });

    it('returns true when SSE has receipts but message read_by is null', () => {
      const messages: TestMessage[] = [
        createTestMessage({ id: 'msg-1', read_by: null }),
      ];

      const sseReadReceipts: ReadReceiptMap = {
        'msg-1': [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
      };

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts,
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.isMessageRead('msg-1')).toBe(true);
    });
  });

  describe('getReadAt helper (lines 164-165)', () => {
    it('returns first read timestamp for a message', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          read_by: [
            { user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' },
            { user_id: 'user-b', read_at: '2024-01-15T10:02:00Z' },
          ],
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.getReadAt('msg-1')).toBe('2024-01-15T10:01:00Z');
    });

    it('returns null for messages without read receipts', () => {
      const messages: TestMessage[] = [
        createTestMessage({ id: 'msg-1', read_by: null }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.getReadAt('msg-1')).toBeNull();
    });

    it('returns null for unknown message IDs', () => {
      const { result } = renderHook(() =>
        useReadReceipts({
          messages: [],
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.getReadAt('unknown-msg')).toBeNull();
    });

    it('prefers SSE receipt timestamp when available', () => {
      const messages: TestMessage[] = [
        createTestMessage({ id: 'msg-1', read_by: null }),
      ];

      const sseReadReceipts: ReadReceiptMap = {
        'msg-1': [{ user_id: 'user-a', read_at: '2024-01-15T10:05:00Z' }],
      };

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts,
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      expect(result.current.getReadAt('msg-1')).toBe('2024-01-15T10:05:00Z');
    });
  });

  describe('edge cases', () => {
    it('handles read_by as non-array', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          // Force non-array value
          read_by: { user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' } as unknown as ReadReceiptEntry[],
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt,
        })
      );

      // Should handle non-array gracefully
      expect(result.current.mergedReadReceipts['msg-1']).toBeUndefined();
    });

    it('handles getCreatedAt returning null', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          sender_id: currentUserId,
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
        }),
      ];

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt: () => null, // Always returns null
        })
      );

      // lastReadMessageId should be null since no valid timestamps
      expect(result.current.lastReadMessageId).toBeNull();
    });

    it('handles NaN timestamp from getCreatedAt', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          sender_id: currentUserId,
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
          created_at: 'not-a-date',
        }),
      ];

      const getCreatedAtWithNaN = (m: TestMessage) => new Date(m.created_at);

      const { result } = renderHook(() =>
        useReadReceipts({
          messages,
          sseReadReceipts: {},
          currentUserId,
          getReadBy,
          isOwnMessage,
          getCreatedAt: getCreatedAtWithNaN,
        })
      );

      // Should skip message with NaN timestamp
      expect(result.current.lastReadMessageId).toBeNull();
    });

    it('maintains consistent helper function behavior across rerenders', () => {
      const messages: TestMessage[] = [
        createTestMessage({
          id: 'msg-1',
          read_by: [{ user_id: 'user-a', read_at: '2024-01-15T10:01:00Z' }],
        }),
      ];

      const { result, rerender } = renderHook(
        ({ msgs }) =>
          useReadReceipts({
            messages: msgs,
            sseReadReceipts: {},
            currentUserId,
            getReadBy,
            isOwnMessage,
            getCreatedAt,
          }),
        { initialProps: { msgs: messages } }
      );

      // Verify behavior before rerender
      expect(result.current.isMessageRead('msg-1')).toBe(true);
      expect(result.current.getReadAt('msg-1')).toBe('2024-01-15T10:01:00Z');

      // Rerender with same messages
      rerender({ msgs: messages });

      // Behavior should be consistent after rerender
      expect(result.current.isMessageRead('msg-1')).toBe(true);
      expect(result.current.getReadAt('msg-1')).toBe('2024-01-15T10:01:00Z');
    });
  });
});
