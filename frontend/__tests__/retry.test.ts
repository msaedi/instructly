import { backoff } from '@/features/shared/api/retry';

describe('backoff', () => {
  it('respects Retry-After header', async () => {
    let calls = 0;
    const start = Date.now();
    const makeRes = (status: number, headers: Record<string, string> = {}) => {
      return {
        status,
        headers: {
          get: (k: string) => headers[k] || null,
        },
      } as unknown as Response;
    };

    const fn = jest.fn(async () => {
      calls++;
      if (calls === 1) {
        return makeRes(429, { 'Retry-After': '1' });
      }
      return makeRes(200);
    });

    const res = await backoff(fn, { maxRetries: 2 });
    const elapsed = Date.now() - start;

    expect(res.status).toBe(200);
    expect(calls).toBe(2);
    expect(elapsed).toBeGreaterThanOrEqual(900); // ~1s
  });
});
