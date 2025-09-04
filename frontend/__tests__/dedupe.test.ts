import { httpJson } from '@/features/shared/api/http';

describe('httpJson inflight dedupe', () => {
  it('returns shared promise for same dedupeKey', async () => {
    const url = '/api/test';

    const originalFetch = global.fetch as unknown as jest.Mock;
    const responseLike = {
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
      headers: { get: (_: string) => null },
    } as unknown as Response;
    const fetchMock = jest.fn(async () => responseLike);
    const g = global as unknown as { fetch: jest.Mock };
    g.fetch = fetchMock;

    const p1 = httpJson<{ ok: boolean }>(url, undefined, undefined, { endpoint: url, dedupeKey: 'k' });
    const p2 = httpJson<{ ok: boolean }>(url, undefined, undefined, { endpoint: url, dedupeKey: 'k' });

    const [r1, r2] = await Promise.all([p1, p2]);
    expect(r1).toEqual({ ok: true });
    expect(r2).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // restore
    const g2 = global as unknown as { fetch: jest.Mock };
    g2.fetch = originalFetch;
  });
});
