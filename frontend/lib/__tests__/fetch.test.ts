import { jest } from '@jest/globals';
import { fetchJson, ApiProblemError } from '@/lib/api/fetch';

function makeResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  const lower: Record<string, string> = {};
  for (const [k, v] of Object.entries({ 'content-type': 'application/json', ...headers })) {
    lower[k.toLowerCase()] = v;
  }
  const make = () =>
    ({
      ok: status >= 200 && status < 300,
      status,
      headers: { get: (k: string) => lower[k.toLowerCase()] ?? null },
      json: async () => body,
      clone: () => make(),
    }) as unknown as Response;
  return make();
}

describe('fetchJson', () => {
  beforeEach(() => {
    jest.restoreAllMocks();
  });

  test('returns parsed JSON on 200', async () => {
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(makeResponse(200, { ok: true }));
    const data = await fetchJson('/test');
    expect(data).toEqual({ ok: true });
  });

  test('throws ApiProblemError on RFC7807 problem+json', async () => {
    const problem = { type: 'about:blank', title: 'Bad Request', status: 400 };
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(
      makeResponse(400, problem, { 'content-type': 'application/problem+json; charset=utf-8' })
    );
    await expect(fetchJson('/bad')).rejects.toBeInstanceOf(ApiProblemError);
  });

  test('throws plain Error on non-problem error', async () => {
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(makeResponse(500, { detail: 'boom' }));
    await expect(fetchJson('/boom')).rejects.toBeInstanceOf(Error);
  });

  test('throws ApiProblemError for FastAPI-style structured detail', async () => {
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(
      makeResponse(429, {
        detail: {
          status: 429,
          code: 'bgc_invite_rate_limited',
          title: 'Background check recently requested',
          message: 'You recently started a background check. Please wait up to 24 hours before trying again.',
        },
      })
    );
    await expect(fetchJson('/limit', { financial: true, retries: 0 })).rejects.toMatchObject({
      problem: expect.objectContaining({
        code: 'bgc_invite_rate_limited',
        detail: expect.stringContaining('Please wait up to 24 hours'),
        status: 429,
      }),
    });
  });

  test('retries once on 429 with jitter and calls onRateLimit', async () => {
    const onRateLimit = jest.fn();
    const first = makeResponse(429, { detail: 'slow down' }, { 'Retry-After': '0' });
    const second = makeResponse(200, { ok: true });
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(first);
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(second);
    const start = Date.now();
    const data = await fetchJson('/rate', { onRateLimit });
    const elapsed = Date.now() - start;
    expect(data).toEqual({ ok: true });
    expect(onRateLimit).toHaveBeenCalled();
    expect(elapsed).toBeGreaterThanOrEqual(400);
  });
});
