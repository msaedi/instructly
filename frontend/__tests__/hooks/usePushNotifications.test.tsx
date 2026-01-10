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

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
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
});
