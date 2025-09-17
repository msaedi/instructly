import { jest } from '@jest/globals';
import { fetchJson, ApiProblemError } from '@/lib/api/fetch';

function makeResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  const lower: Record<string, string> = {};
  for (const [k, v] of Object.entries({ 'content-type': 'application/json', ...headers })) {
    lower[k.toLowerCase()] = v;
  }
  const res: { ok: boolean; status: number; headers: { get: (k: string) => string | null }; json: () => Promise<unknown>; clone: () => unknown } = {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k: string) => lower[k.toLowerCase()] ?? null },
    json: async () => body,
    clone: () => undefined as unknown,
  };
  return res;
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
