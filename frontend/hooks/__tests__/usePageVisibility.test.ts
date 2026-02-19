import { renderHook, act } from '@testing-library/react';
import { usePageVisibility } from '../usePageVisibility';

describe('usePageVisibility', () => {
  const originalVisibilityState = Object.getOwnPropertyDescriptor(
    Document.prototype,
    'visibilityState'
  );

  let visibilityChangeHandlers: EventListener[];

  beforeEach(() => {
    visibilityChangeHandlers = [];

    jest.spyOn(document, 'addEventListener').mockImplementation(
      (event: string, handler: EventListenerOrEventListenerObject) => {
        if (event === 'visibilitychange' && typeof handler === 'function') {
          visibilityChangeHandlers.push(handler as EventListener);
        }
      }
    );

    jest.spyOn(document, 'removeEventListener').mockImplementation(
      (event: string, handler: EventListenerOrEventListenerObject) => {
        if (event === 'visibilitychange' && typeof handler === 'function') {
          const index = visibilityChangeHandlers.indexOf(handler as EventListener);
          if (index > -1) {
            visibilityChangeHandlers.splice(index, 1);
          }
        }
      }
    );
  });

  afterEach(() => {
    jest.restoreAllMocks();
    if (originalVisibilityState) {
      Object.defineProperty(Document.prototype, 'visibilityState', originalVisibilityState);
    }
  });

  const setVisibilityState = (state: 'visible' | 'hidden') => {
    Object.defineProperty(document, 'visibilityState', {
      value: state,
      configurable: true,
    });
  };

  const triggerVisibilityChange = () => {
    const event = new Event('visibilitychange');
    visibilityChangeHandlers.forEach((handler) => handler(event));
  };

  it('returns true when page is visible', () => {
    setVisibilityState('visible');
    const { result } = renderHook(() => usePageVisibility());

    expect(result.current).toBe(true);
  });

  it('returns false when page is hidden', () => {
    setVisibilityState('hidden');
    const { result } = renderHook(() => usePageVisibility());

    expect(result.current).toBe(false);
  });

  it('updates when visibility changes from visible to hidden', () => {
    setVisibilityState('visible');
    const { result } = renderHook(() => usePageVisibility());

    expect(result.current).toBe(true);

    act(() => {
      setVisibilityState('hidden');
      triggerVisibilityChange();
    });

    expect(result.current).toBe(false);
  });

  it('updates when visibility changes from hidden to visible', () => {
    setVisibilityState('hidden');
    const { result } = renderHook(() => usePageVisibility());

    expect(result.current).toBe(false);

    act(() => {
      setVisibilityState('visible');
      triggerVisibilityChange();
    });

    expect(result.current).toBe(true);
  });

  it('subscribes to visibilitychange event on mount', () => {
    setVisibilityState('visible');
    renderHook(() => usePageVisibility());

    expect(document.addEventListener).toHaveBeenCalledWith(
      'visibilitychange',
      expect.any(Function)
    );
  });

  it('unsubscribes from visibilitychange event on unmount', () => {
    setVisibilityState('visible');
    const { unmount } = renderHook(() => usePageVisibility());

    unmount();

    expect(document.removeEventListener).toHaveBeenCalledWith(
      'visibilitychange',
      expect.any(Function)
    );
  });

  it('handles multiple visibility changes', () => {
    setVisibilityState('visible');
    const { result } = renderHook(() => usePageVisibility());

    expect(result.current).toBe(true);

    act(() => {
      setVisibilityState('hidden');
      triggerVisibilityChange();
    });
    expect(result.current).toBe(false);

    act(() => {
      setVisibilityState('visible');
      triggerVisibilityChange();
    });
    expect(result.current).toBe(true);

    act(() => {
      setVisibilityState('hidden');
      triggerVisibilityChange();
    });
    expect(result.current).toBe(false);
  });

  it('uses server snapshot (getServerSnapshot) returning true during SSR', () => {
    // The third argument to useSyncExternalStore is getServerSnapshot,
    // which returns true (assumes page is visible on server).
    // In JSDOM, document exists so the server snapshot is not normally called.
    // We test it by mocking useSyncExternalStore to invoke getServerSnapshot.
    const useSyncExternalStoreSpy = jest.spyOn(
      require('react'),
      'useSyncExternalStore'
    );

    // Call the hook to register the spy
    setVisibilityState('visible');
    renderHook(() => usePageVisibility());

    // The third argument should be the getServerSnapshot function
    expect(useSyncExternalStoreSpy).toHaveBeenCalled();
    const lastCall = useSyncExternalStoreSpy.mock.calls[useSyncExternalStoreSpy.mock.calls.length - 1];
    expect(lastCall).toBeDefined();

    // lastCall[2] is getServerSnapshot - it should return true
    const getServerSnapshot = lastCall?.[2] as (() => boolean) | undefined;
    expect(getServerSnapshot).toBeDefined();
    expect(getServerSnapshot?.()).toBe(true);

    useSyncExternalStoreSpy.mockRestore();
  });
});
