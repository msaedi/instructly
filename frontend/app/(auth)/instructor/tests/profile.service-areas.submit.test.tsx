import { submitServiceAreasOnce } from '@/app/(auth)/instructor/profile/serviceAreaSubmit';
import type { FetchWithAuthFn } from '@/app/(auth)/instructor/profile/serviceAreaSubmit';

describe('submitServiceAreasOnce', () => {
  it('guards against concurrent submissions', async () => {
    const payload = { neighborhood_ids: ['MN01', 'MN02'] };
    const inFlightRef = { current: false };
    const setSaving = jest.fn();

    let resolveFetch: (() => void) | undefined;
    const fetcher = jest.fn(() =>
      new Promise((resolve) => {
        resolveFetch = () => resolve({});
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

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(setSaving).toHaveBeenCalledWith(true);

    resolveFetch?.();
    await Promise.all([first, second]);

    expect(setSaving).toHaveBeenCalledTimes(2);
    expect(setSaving).toHaveBeenLastCalledWith(false);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(inFlightRef.current).toBe(false);
  });
});
