import { subscribeSharedTicker } from '../useSharedTicker';

describe('useSharedTicker helpers', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it('ticks subscribers and clears the interval when the last listener unsubscribes', () => {
    const listener = jest.fn();
    const clearIntervalSpy = jest.spyOn(global, 'clearInterval');

    const unsubscribe = subscribeSharedTicker(listener);
    jest.advanceTimersByTime(1000);
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    expect(clearIntervalSpy).toHaveBeenCalledTimes(1);
  });

  it('does not throw if unsubscribe runs after the ticker is already idle', () => {
    const unsubscribe = subscribeSharedTicker(() => undefined);
    unsubscribe();

    expect(() => unsubscribe()).not.toThrow();
  });
});
