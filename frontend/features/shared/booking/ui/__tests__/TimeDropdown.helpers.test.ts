import { clearPendingCloseTimeout } from '../TimeDropdown.helpers';

describe('TimeDropdown helpers', () => {
  it('clears a pending close timeout and resets the ref', () => {
    const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
    const closeTimeoutRef = {
      current: setTimeout(() => {}, 1000),
    };

    clearPendingCloseTimeout(closeTimeoutRef);

    expect(clearTimeoutSpy).toHaveBeenCalled();
    expect(closeTimeoutRef.current).toBeNull();
  });

  it('no-ops when there is no pending timeout', () => {
    const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');
    const closeTimeoutRef = { current: null as ReturnType<typeof setTimeout> | null };

    clearPendingCloseTimeout(closeTimeoutRef);

    expect(clearTimeoutSpy).not.toHaveBeenCalled();
    expect(closeTimeoutRef.current).toBeNull();
  });
});
