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
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
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

    const dataPromise = fetchJson('/rate', { onRateLimit });
    // Advance timers to handle the retry delay
    await jest.runAllTimersAsync();
    const data = await dataPromise;

    expect(data).toEqual({ ok: true });
    expect(onRateLimit).toHaveBeenCalled();
  });

  test('retries multiple times until max retries with persistent 429', async () => {
    // Use real timers for this test since it has complex async retry logic
    jest.useRealTimers();

    const onRateLimit = jest.fn();
    // When retries=2, the flow is:
    // 1. run() gets 429, calls onRateLimit(attempt=1), retries inside run(), gets 429
    // 2. while loop (attempt=1): attempt++ to 2, onRateLimit(attempt=2), fetch 429
    // 3. while loop (attempt=2): attempt++ to 3, onRateLimit(attempt=3), fetch 429
    // 4. loop exits (3 <= 2 is false), throws error
    // So we need 4 mocked responses and expect 3 onRateLimit calls
    const r1 = makeResponse(429, { detail: 'slow' }, { 'Retry-After': '0' });
    const r2 = makeResponse(429, { detail: 'slow' }, { 'Retry-After': '0' });
    const r3 = makeResponse(429, { detail: 'slow' }, { 'Retry-After': '0' });
    const r4 = makeResponse(429, { detail: 'slow' }, { 'Retry-After': '0' });
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(r1);
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(r2);
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(r3);
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(r4);

    await expect(fetchJson('/rate', { onRateLimit, retries: 2 })).rejects.toBeInstanceOf(Error);
    expect(onRateLimit).toHaveBeenCalledTimes(3);
  });

  test('retries with custom retry count and succeeds on final attempt', async () => {
    const onRateLimit = jest.fn();
    const first = makeResponse(429, { detail: 'slow' }, { 'Retry-After': '0' });
    const second = makeResponse(429, { detail: 'slow' }, { 'Retry-After': '0' });
    const third = makeResponse(200, { ok: true });
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(first);
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(second);
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(third);

    const dataPromise = fetchJson('/rate', { onRateLimit, retries: 2 });
    await jest.runAllTimersAsync();
    const data = await dataPromise;
    expect(data).toEqual({ ok: true });
  });

  test('handles AbortError gracefully', async () => {
    const abortError = new DOMException('The operation was aborted', 'AbortError');
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockRejectedValueOnce: (v: unknown) => unknown }).mockRejectedValueOnce(abortError);
    const data = await fetchJson('/abort');
    expect(data).toBeUndefined();
  });

  test('normalizes error with code field at top level', async () => {
    const body = { code: 'some_error_code', title: 'Some Error' };
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(makeResponse(400, body));
    await expect(fetchJson('/code-error')).rejects.toMatchObject({
      problem: expect.objectContaining({
        code: 'some_error_code',
      }),
    });
  });

  test('handles non-JSON response gracefully', async () => {
    const response = {
      ok: true,
      status: 200,
      headers: { get: (k: string) => k === 'content-type' ? 'text/plain' : null },
      json: async () => { throw new Error('Invalid JSON'); },
      clone: function() { return this; },
    } as unknown as Response;
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(response);
    const data = await fetchJson('/text');
    expect(data).toBeUndefined();
  });

  test('uses Retry-After header value for wait time', async () => {
    const onRateLimit = jest.fn();
    const first = makeResponse(429, { detail: 'slow' }, { 'Retry-After': '1' });
    const second = makeResponse(200, { ok: true });
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(first);
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(second);

    const dataPromise = fetchJson('/rate', { onRateLimit });
    // Advance timers to handle the Retry-After delay
    await jest.runAllTimersAsync();
    const data = await dataPromise;
    expect(data).toEqual({ ok: true });
    expect(onRateLimit).toHaveBeenCalled();
  });

  test('deduplicates requests with same dedupeKey', async () => {
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    const mockImpl = async () => {
      return makeResponse(200, { ok: true });
    };
    (fetchSpy as unknown as { mockImplementation: (fn: unknown) => unknown }).mockImplementation(mockImpl);

    const promise1 = fetchJson('/test', { dedupeKey: 'same-key' });
    const promise2 = fetchJson('/test', { dedupeKey: 'same-key' });
    await jest.runAllTimersAsync();
    const [r1, r2] = await Promise.all([promise1, promise2]);

    expect(r1).toEqual({ ok: true });
    expect(r2).toEqual({ ok: true });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  test('financial flag skips internal retry in run() on 429', async () => {
    // With financial=true, run() returns immediately on 429 without the internal sleep+retry
    // But the outer while loop still retries based on maxRetries
    // With retries: 0, there should be no outer loop retries
    const r1 = makeResponse(429, { detail: 'rate limited' }, { 'Retry-After': '1' });
    const fetchSpy = jest.spyOn(global as unknown as { fetch: typeof fetch }, 'fetch');
    (fetchSpy as unknown as { mockResolvedValueOnce: (v: unknown) => unknown }).mockResolvedValueOnce(r1);
    await expect(fetchJson('/financial', { financial: true, retries: 0 })).rejects.toThrow();
    // Only 1 fetch call since financial=true skips internal retry and retries=0 skips outer loop
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });
});
