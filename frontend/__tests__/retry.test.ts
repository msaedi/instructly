import { backoff } from '@/features/shared/api/retry';

describe('backoff', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  const makeRes = (status: number, headers: Record<string, string> = {}) => {
    return {
      status,
      headers: {
        get: (k: string) => headers[k] ?? null,
      },
    } as unknown as Response;
  };

  it('respects Retry-After header', async () => {
    let calls = 0;
    const setTimeoutSpy = jest.spyOn(global, 'setTimeout');

    const fn = jest.fn(async () => {
      calls++;
      if (calls === 1) {
        return makeRes(429, { 'Retry-After': '1' });
      }
      return makeRes(200);
    });

    const resPromise = backoff(fn, { maxRetries: 2 });
    await jest.runAllTimersAsync();
    const res = await resPromise;

    expect(res.status).toBe(200);
    expect(calls).toBe(2);
    expect(setTimeoutSpy).toHaveBeenCalledTimes(1);
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 1000);
    setTimeoutSpy.mockRestore();
  });

  it('returns 429 response when max retries exceeded', async () => {
    let calls = 0;
    const setTimeoutSpy = jest.spyOn(global, 'setTimeout');
    const fn = jest.fn(async () => {
      calls++;
      return makeRes(429, { 'Retry-After': '0' }); // Always return 429
    });

    const resPromise = backoff(fn, { maxRetries: 1 });
    await jest.runAllTimersAsync();
    const res = await resPromise;

    expect(res.status).toBe(429);
    expect(calls).toBe(2); // Initial + 1 retry
    expect(setTimeoutSpy).toHaveBeenCalledTimes(2);
    expect(setTimeoutSpy).toHaveBeenNthCalledWith(1, expect.any(Function), 1000);
    expect(setTimeoutSpy).toHaveBeenNthCalledWith(2, expect.any(Function), 2000);
    setTimeoutSpy.mockRestore();
  });

  it('works with no options passed (uses defaults)', async () => {
    // This test just verifies the function works when called without options
    // It returns immediately on success so no timeout issues
    const setTimeoutSpy = jest.spyOn(global, 'setTimeout');
    const fn = jest.fn(async () => makeRes(200));

    const res = await backoff(fn);

    expect(res.status).toBe(200);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(setTimeoutSpy).not.toHaveBeenCalled();
    setTimeoutSpy.mockRestore();
  });

  it('returns immediately on non-429 status', async () => {
    const setTimeoutSpy = jest.spyOn(global, 'setTimeout');
    const fn = jest.fn(async () => makeRes(500));

    const res = await backoff(fn, { maxRetries: 3 });

    expect(res.status).toBe(500);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(setTimeoutSpy).not.toHaveBeenCalled();
    setTimeoutSpy.mockRestore();
  });

  it('uses exponential backoff delay when no Retry-After header', async () => {
    let calls = 0;
    const setTimeoutSpy = jest.spyOn(global, 'setTimeout');
    const fn = jest.fn(async () => {
      calls++;
      if (calls === 1) {
        return makeRes(429); // No Retry-After header
      }
      return makeRes(200);
    });

    const resPromise = backoff(fn, { maxRetries: 2 });
    await jest.runAllTimersAsync();
    const res = await resPromise;

    expect(res.status).toBe(200);
    expect(setTimeoutSpy).toHaveBeenCalledTimes(1);
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 1000);
    setTimeoutSpy.mockRestore();
  });
});
