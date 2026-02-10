import { backoff } from '../retry';

describe('backoff', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns immediately on non-429 response', async () => {
    const fn = jest.fn().mockResolvedValue({ status: 200 });

    const result = await backoff(fn);

    expect(result).toEqual({ status: 200 });
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('uses default maxRetries of 3 when opts is omitted', async () => {
    let call = 0;
    const fn = jest.fn().mockImplementation(() => {
      call++;
      if (call <= 4) {
        return Promise.resolve({
          status: 429,
          headers: new Map([['Retry-After', '0']]),
        });
      }
      return Promise.resolve({ status: 200 });
    });

    // Run with explicit empty-ish opts to hit the ?? 3 branch
    const promise = backoff(fn, {});
    // Flush all timers for the retries
    for (let i = 0; i < 5; i++) {
      await Promise.resolve();
      jest.advanceTimersByTime(60_000);
      await Promise.resolve();
    }
    const result = await promise;

    // After 3 retries (4 total calls), it should give up and return the 429
    expect(result.status).toBe(429);
    expect(fn).toHaveBeenCalledTimes(4);
  });

  it('respects Retry-After header', async () => {
    let call = 0;
    const fn = jest.fn().mockImplementation(() => {
      call++;
      if (call === 1) {
        return Promise.resolve({
          status: 429,
          headers: { get: () => '5' },
        });
      }
      return Promise.resolve({ status: 200, headers: { get: () => null } });
    });

    const promise = backoff(fn, { maxRetries: 3 });
    await Promise.resolve();
    jest.advanceTimersByTime(5000);
    await Promise.resolve();
    const result = await promise;

    expect(result.status).toBe(200);
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
