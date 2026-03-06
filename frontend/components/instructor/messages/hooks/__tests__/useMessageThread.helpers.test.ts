import { applyDeliveryUpdate, syncStaleThreads } from '../useMessageThread.helpers';

describe('useMessageThread helpers', () => {
  it('marks only advanced seen threads as stale', () => {
    const lastSeen = new Map<string, number>([['seen', 100]]);
    const stale = new Set<string>();

    syncStaleThreads(
      [
        { id: 'seen', latestMessageAt: 200 } as never,
        { id: 'unseen', latestMessageAt: 500 } as never,
        { id: '', latestMessageAt: 999 } as never,
      ],
      lastSeen,
      stale,
    );

    expect(Array.from(stale)).toEqual(['seen']);
  });

  it('creates a delivered message when the collection is empty', () => {
    const delivered = {
      id: 'server-1',
      delivered_at: '2025-01-01T10:00:00Z',
      delivery: { status: 'delivered', timeLabel: '10:00 AM' },
    } as never;

    expect(applyDeliveryUpdate([], delivered, 'optimistic-1')).toEqual([delivered]);
  });

  it('appends the delivered message if the optimistic message is missing', () => {
    const delivered = {
      id: 'server-1',
      delivered_at: '2025-01-01T10:00:00Z',
      delivery: { status: 'delivered', timeLabel: '10:00 AM' },
    } as never;

    const updated = applyDeliveryUpdate(
      [{ id: 'different-message', delivery: null, delivered_at: null } as never],
      delivered,
      'optimistic-1',
      'server-1',
    );

    expect(updated).toHaveLength(2);
    expect(updated[1]).toEqual(delivered);
  });

  it('replaces the optimistic message when the server delivery arrives', () => {
    const delivered = {
      id: 'server-1',
      delivered_at: '2025-01-01T10:00:00Z',
      delivery: { status: 'delivered', timeLabel: '10:00 AM' },
    } as never;

    const updated = applyDeliveryUpdate(
      [{ id: 'optimistic-1', delivery: { status: 'sending' }, delivered_at: null } as never],
      delivered,
      'optimistic-1',
      'server-1',
    );

    expect(updated).toEqual([delivered]);
  });
});
