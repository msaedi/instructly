import { submitServiceAreasOnce } from '@/app/(auth)/instructor/profile/serviceAreaSubmit';
import type { FetchWithAuthFn } from '@/app/(auth)/instructor/profile/serviceAreaSubmit';

describe('submitServiceAreasOnce', () => {
  it('guards against concurrent submissions', async () => {
    const payload = { neighborhood_ids: ['MN01', 'MN02'] };
    const inFlightRef = { current: false };
    // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
    const setSaving: jest.Mock<void, [boolean]> = jest.fn();

    let resolveFetch: (() => void) | undefined;
    // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
    const fetcher: jest.Mock<Promise<{ ok: boolean }>, []> = jest.fn(() =>
      new Promise((resolve) => {
        resolveFetch = () => resolve({ ok: true });
      })
    );

    const first = submitServiceAreasOnce({
      fetcher: fetcher as unknown as FetchWithAuthFn,
      payload,
      inFlightRef,
      setSaving,
    });
    const second = submitServiceAreasOnce({
      fetcher: fetcher as unknown as FetchWithAuthFn,
      payload,
      inFlightRef,
      setSaving,
    });

    // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
    expect(fetcher).toHaveBeenCalledTimes(1);
    // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
    expect(setSaving).toHaveBeenCalledWith(true);

    resolveFetch?.();
    await Promise.all([first, second]);

    // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
    expect(setSaving).toHaveBeenCalledTimes(2);
    // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
    expect(setSaving).toHaveBeenLastCalledWith(false);
    // type-coverage:ignore-next-line -- jest.Mock inherits Function which contains any
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(inFlightRef.current).toBe(false);
  });
});
