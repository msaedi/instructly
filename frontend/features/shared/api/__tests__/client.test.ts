import { protectedApi } from '@/features/shared/api/client';

describe('protectedApi.getBookings', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('normalizes lowercase status queries to uppercase BookingStatus', async () => {
    await protectedApi.getBookings({ status: 'completed', limit: 1 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('status')).toBe('COMPLETED');
  });
});
