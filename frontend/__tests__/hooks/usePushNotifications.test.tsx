import { act, renderHook, waitFor } from '@testing-library/react';
import { usePushNotifications } from '@/features/shared/hooks/usePushNotifications';
import { pushNotificationApi } from '@/features/shared/api/pushNotifications';

jest.mock('@/features/shared/api/pushNotifications', () => ({
  pushNotificationApi: {
    getVapidPublicKey: jest.fn().mockResolvedValue('mock-vapid-key'),
    subscribe: jest.fn().mockResolvedValue(undefined),
    unsubscribe: jest.fn().mockResolvedValue(undefined),
    getSubscriptions: jest.fn().mockResolvedValue([]),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

const mockUseAuth = jest.fn().mockReturnValue({ isAuthenticated: true });
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => mockUseAuth(),
}));

describe('usePushNotifications', () => {
  const originalNotification = window.Notification;
  const originalServiceWorker = navigator.serviceWorker;
  const originalPushManager = (window as unknown as { PushManager?: unknown }).PushManager;

  const mockServiceWorker = {
    register: jest.fn(),
  };

  const mockPushManager = {
    getSubscription: jest.fn(),
    subscribe: jest.fn(),
  };

  const mockRegistration = {
    scope: '/',
    pushManager: mockPushManager,
  };

  const mockedApi = pushNotificationApi as jest.Mocked<typeof pushNotificationApi>;

  beforeEach(() => {
    jest.clearAllMocks();

    // Reset mockUseAuth to default authenticated state
    mockUseAuth.mockReturnValue({ isAuthenticated: true });

    Object.defineProperty(navigator, 'serviceWorker', {
      value: mockServiceWorker,
      configurable: true,
    });

    Object.defineProperty(window, 'PushManager', {
      value: jest.fn(),
      configurable: true,
      writable: true,
    });

    Object.defineProperty(window, 'Notification', {
      value: {
        permission: 'granted',
        requestPermission: jest.fn().mockResolvedValue('granted'),
      },
      configurable: true,
      writable: true,
    });

    mockServiceWorker.register.mockResolvedValue(mockRegistration);
    mockPushManager.getSubscription.mockResolvedValue(null);

    mockedApi.getVapidPublicKey.mockResolvedValue('mock-vapid-key');
    mockedApi.subscribe.mockResolvedValue(undefined);
    mockedApi.unsubscribe.mockResolvedValue(undefined);
  });

  afterEach(() => {
    Object.defineProperty(navigator, 'serviceWorker', {
      value: originalServiceWorker,
      configurable: true,
    });

    if (originalPushManager !== undefined) {
      Object.defineProperty(window, 'PushManager', {
        value: originalPushManager,
        configurable: true,
        writable: true,
      });
    } else {
      delete (window as unknown as { PushManager?: unknown }).PushManager;
    }

    if (originalNotification !== undefined) {
      Object.defineProperty(window, 'Notification', {
        value: originalNotification,
        configurable: true,
        writable: true,
      });
    } else {
      delete (window as unknown as { Notification?: unknown }).Notification;
    }
  });

  it('detects browser support', async () => {
    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
  });

  it('detects unsupported browser', async () => {
    delete (window as unknown as { PushManager?: unknown }).PushManager;

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(false);
      expect(result.current.permission).toBe('unsupported');
    });
  });

  it('detects existing subscription', async () => {
    mockPushManager.getSubscription.mockResolvedValue({ endpoint: 'https://example.com' });

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSubscribed).toBe(true);
    });
  });

  it('handles subscribe flow', async () => {
    const mockSubscription = {
      endpoint: 'https://fcm.googleapis.com/test',
      getKey: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3]).buffer),
      unsubscribe: jest.fn().mockResolvedValue(true),
    };
    mockPushManager.subscribe.mockResolvedValue(mockSubscription);

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(true);
    });

    expect(result.current.isSubscribed).toBe(true);
    expect(mockedApi.subscribe).toHaveBeenCalled();
  });

  it('sets permission to unsupported when Notification is not in window', async () => {
    delete (window as unknown as { Notification?: unknown }).Notification;

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.permission).toBe('unsupported');
    });
  });

  it('handles service worker registration failure', async () => {
    const { logger } = jest.requireMock('@/lib/logger') as { logger: { error: jest.Mock } };
    mockServiceWorker.register.mockRejectedValue(new Error('SW registration failed'));

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.error).toBe('Failed to register service worker');
    });
    expect(logger.error).toHaveBeenCalledWith(
      '[Push] Service worker registration failed',
      expect.any(Error)
    );
  });

  it('checkSubscription updates isSubscribed state', async () => {
    const mockSubscription = { endpoint: 'https://example.com' };
    mockPushManager.getSubscription
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(mockSubscription);

    const { result } = renderHook(() => usePushNotifications());

    // Wait for full initialization (swRegistration must be set)
    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    await act(async () => {
      await result.current.checkSubscription();
    });

    expect(result.current.isSubscribed).toBe(true);
  });

  it('checkSubscription handles errors gracefully', async () => {
    const { logger } = jest.requireMock('@/lib/logger') as { logger: { error: jest.Mock } };
    mockPushManager.getSubscription
      .mockResolvedValueOnce(null)
      .mockRejectedValueOnce(new Error('Failed'));

    const { result } = renderHook(() => usePushNotifications());

    // Wait for full initialization (swRegistration must be set)
    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    await act(async () => {
      await result.current.checkSubscription();
    });

    expect(logger.error).toHaveBeenCalledWith(
      '[Push] Failed to check subscription',
      expect.any(Error)
    );
  });

  it('subscribe returns false when not authenticated', async () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false });

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });

    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Push notifications not available');
  });

  it('subscribe returns false when Notification not in window', async () => {
    const { result } = renderHook(() => usePushNotifications());

    // Wait for full initialization (swRegistration must be set)
    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    // Delete Notification after swRegistration is set
    delete (window as unknown as { Notification?: unknown }).Notification;

    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Push notifications are not supported');
  });

  describe('permission handling', () => {
    it('subscribe handles permission request denial', async () => {
      // Set up mock BEFORE rendering hook
      Object.defineProperty(window, 'Notification', {
        value: {
          permission: 'default',
          requestPermission: jest.fn().mockResolvedValue('denied'),
        },
        configurable: true,
        writable: true,
      });

      const mockSubscription = {
        endpoint: 'https://fcm.googleapis.com/test',
        getKey: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3]).buffer),
      };
      mockPushManager.subscribe.mockResolvedValue(mockSubscription);

      const { result } = renderHook(() => usePushNotifications());

      await waitFor(() => {
        expect(result.current.isSupported).toBe(true);
      });
      await waitFor(() => {
        expect(mockPushManager.getSubscription).toHaveBeenCalled();
      });

      await act(async () => {
        const success = await result.current.subscribe();
        expect(success).toBe(false);
      });

      expect(result.current.permission).toBe('denied');
      expect(result.current.error).toBe('Notification permission denied');
    });

    it('subscribe handles already denied permission', async () => {
      // Set up mock BEFORE rendering hook
      Object.defineProperty(window, 'Notification', {
        value: {
          permission: 'denied',
          requestPermission: jest.fn(),
        },
        configurable: true,
        writable: true,
      });

      const { result } = renderHook(() => usePushNotifications());

      await waitFor(() => {
        expect(result.current.isSupported).toBe(true);
      });
      await waitFor(() => {
        expect(mockPushManager.getSubscription).toHaveBeenCalled();
      });

      await act(async () => {
        const success = await result.current.subscribe();
        expect(success).toBe(false);
      });

      expect(result.current.permission).toBe('denied');
      expect(result.current.error).toBe(
        'Notification permission was denied. Please enable it in browser settings.'
      );
    });
  });

  it('subscribe handles subscription error', async () => {
    const { logger } = jest.requireMock('@/lib/logger') as { logger: { error: jest.Mock } };
    mockPushManager.subscribe.mockRejectedValue(new Error('Subscription failed'));

    const { result } = renderHook(() => usePushNotifications());

    // Wait for full initialization
    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Subscription failed');
    expect(logger.error).toHaveBeenCalledWith('[Push] Subscription failed', expect.any(Error));
  });

  it('subscribe handles non-Error exception', async () => {
    mockPushManager.subscribe.mockRejectedValue('string error');

    const { result } = renderHook(() => usePushNotifications());

    // Wait for full initialization
    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Failed to subscribe');
  });

  it('unsubscribe returns false when swRegistration is null', async () => {
    delete (window as unknown as { PushManager?: unknown }).PushManager;

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(false);
    });

    await act(async () => {
      const success = await result.current.unsubscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Push notifications not available');
  });

  it('unsubscribe handles successful flow', async () => {
    const mockSubscription = {
      endpoint: 'https://fcm.googleapis.com/test',
      unsubscribe: jest.fn().mockResolvedValue(true),
      getKey: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3]).buffer),
    };
    mockPushManager.getSubscription.mockResolvedValue(mockSubscription);

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSubscribed).toBe(true);
    });

    await act(async () => {
      const success = await result.current.unsubscribe();
      expect(success).toBe(true);
    });

    expect(result.current.isSubscribed).toBe(false);
    expect(mockSubscription.unsubscribe).toHaveBeenCalled();
    expect(mockedApi.unsubscribe).toHaveBeenCalledWith(mockSubscription.endpoint);
  });

  it('unsubscribe continues when backend unsubscribe fails', async () => {
    const { logger } = jest.requireMock('@/lib/logger') as { logger: { warn: jest.Mock } };
    const mockSubscription = {
      endpoint: 'https://fcm.googleapis.com/test',
      unsubscribe: jest.fn().mockResolvedValue(true),
      getKey: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3]).buffer),
    };
    mockPushManager.getSubscription.mockResolvedValue(mockSubscription);
    mockedApi.unsubscribe.mockRejectedValue(new Error('Backend failed'));

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSubscribed).toBe(true);
    });

    await act(async () => {
      const success = await result.current.unsubscribe();
      expect(success).toBe(true);
    });

    expect(logger.warn).toHaveBeenCalledWith('[Push] Backend unsubscribe failed', expect.any(Error));
    expect(result.current.isSubscribed).toBe(false);
  });

  it('unsubscribe handles no existing subscription', async () => {
    mockPushManager.getSubscription
      .mockResolvedValueOnce({ endpoint: 'https://example.com' })
      .mockResolvedValueOnce(null);

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSubscribed).toBe(true);
    });

    await act(async () => {
      const success = await result.current.unsubscribe();
      expect(success).toBe(true);
    });

    expect(result.current.isSubscribed).toBe(false);
  });

  it('unsubscribe handles error during unsubscribe', async () => {
    const { logger } = jest.requireMock('@/lib/logger') as { logger: { error: jest.Mock } };
    const mockSubscription = {
      endpoint: 'https://fcm.googleapis.com/test',
      unsubscribe: jest.fn().mockRejectedValue(new Error('Unsubscribe failed')),
      getKey: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3]).buffer),
    };
    mockPushManager.getSubscription.mockResolvedValue(mockSubscription);

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSubscribed).toBe(true);
    });

    await act(async () => {
      const success = await result.current.unsubscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Unsubscribe failed');
    expect(logger.error).toHaveBeenCalledWith('[Push] Unsubscribe failed', expect.any(Error));
  });

  it('unsubscribe handles non-Error exception', async () => {
    const mockSubscription = {
      endpoint: 'https://fcm.googleapis.com/test',
      unsubscribe: jest.fn().mockRejectedValue('string error'),
      getKey: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3]).buffer),
    };
    mockPushManager.getSubscription.mockResolvedValue(mockSubscription);

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSubscribed).toBe(true);
    });

    await act(async () => {
      const success = await result.current.unsubscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Failed to unsubscribe');
  });

  it('sets isLoading during subscribe', async () => {
    let resolveSubscribe: () => void;
    const subscribePromise = new Promise<{ endpoint: string; getKey: () => ArrayBuffer }>(
      (resolve) => {
        resolveSubscribe = () =>
          resolve({
            endpoint: 'https://test.com',
            getKey: () => new Uint8Array([1, 2, 3]).buffer,
          });
      }
    );
    mockPushManager.subscribe.mockReturnValue(subscribePromise);

    const { result } = renderHook(() => usePushNotifications());

    // Wait for full initialization (including swRegistration being set)
    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    act(() => {
      void result.current.subscribe();
    });

    // Need to wait for the async function to start
    await waitFor(() => {
      expect(result.current.isLoading).toBe(true);
    });

    await act(async () => {
      resolveSubscribe!();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  it('checkSubscription is a no-op when swRegistration is null', async () => {
    // Simulate a case where serviceWorker.register fails,
    // so swRegistration remains null even though isSupported is true
    mockServiceWorker.register.mockRejectedValue(new Error('SW register fail'));

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.error).toBe('Failed to register service worker');
    });

    // Clear mock calls from init
    mockPushManager.getSubscription.mockClear();

    // checkSubscription should early return since swRegistration is null
    await act(async () => {
      await result.current.checkSubscription();
    });

    // getSubscription should NOT have been called again
    expect(mockPushManager.getSubscription).not.toHaveBeenCalled();
  });

  it('subscribe handles getKey returning null buffer', async () => {
    const mockSubscription = {
      endpoint: 'https://fcm.googleapis.com/test',
      getKey: jest.fn().mockReturnValue(null), // null ArrayBuffer
      unsubscribe: jest.fn().mockResolvedValue(true),
    };
    mockPushManager.subscribe.mockResolvedValue(mockSubscription);

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(true);
    });

    // arrayBufferToBase64 with null should return ''
    expect(mockedApi.subscribe).toHaveBeenCalledWith(
      expect.objectContaining({
        endpoint: 'https://fcm.googleapis.com/test',
        p256dh: '',
        auth: '',
      })
    );
  });

  it('subscribe skips permission request when already granted', async () => {
    // Notification.permission is 'granted' (set in beforeEach), so
    // neither the 'default' nor 'denied' branch should run
    const mockSubscription = {
      endpoint: 'https://fcm.googleapis.com/test-granted',
      getKey: jest.fn().mockReturnValue(new Uint8Array([4, 5, 6]).buffer),
      unsubscribe: jest.fn().mockResolvedValue(true),
    };
    mockPushManager.subscribe.mockResolvedValue(mockSubscription);

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
    });
    await waitFor(() => {
      expect(mockPushManager.getSubscription).toHaveBeenCalled();
    });

    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(true);
    });

    // requestPermission should NOT have been called since it was already granted
    expect((window.Notification as unknown as { requestPermission: jest.Mock }).requestPermission).not.toHaveBeenCalled();
    expect(result.current.isSubscribed).toBe(true);
  });

  it('subscribe returns false when swRegistration is null but isSupported is true', async () => {
    // This happens when SW registration fails
    mockServiceWorker.register.mockRejectedValue(new Error('SW fail'));

    const { result } = renderHook(() => usePushNotifications());

    await waitFor(() => {
      expect(result.current.isSupported).toBe(true);
      expect(result.current.error).toBe('Failed to register service worker');
    });

    // Clear error so we can see the subscribe error
    await act(async () => {
      const success = await result.current.subscribe();
      expect(success).toBe(false);
    });

    expect(result.current.error).toBe('Push notifications not available');
  });

});
