'use client';

import { useCallback, useEffect, useState } from 'react';
import { pushNotificationApi } from '@/features/shared/api/pushNotifications';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { logger } from '@/lib/logger';

type PushPermissionState = 'prompt' | 'granted' | 'denied' | 'unsupported';

interface UsePushNotificationsReturn {
  /** Whether push notifications are supported in this browser */
  isSupported: boolean;
  /** Current permission state */
  permission: PushPermissionState;
  /** Whether user has an active subscription */
  isSubscribed: boolean;
  /** Whether an operation is in progress */
  isLoading: boolean;
  /** Any error that occurred */
  error: string | null;
  /** Request permission and subscribe to push */
  subscribe: () => Promise<boolean>;
  /** Unsubscribe from push notifications */
  unsubscribe: () => Promise<boolean>;
  /** Check current subscription status */
  checkSubscription: () => Promise<void>;
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function arrayBufferToBase64(buffer: ArrayBuffer | null): string {
  if (!buffer) return '';
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i] ?? 0);
  }
  return window.btoa(binary);
}

export function usePushNotifications(): UsePushNotificationsReturn {
  const { isAuthenticated } = useAuth();
  const [isSupported, setIsSupported] = useState(false);
  const [permission, setPermission] = useState<PushPermissionState>('prompt');
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [swRegistration, setSwRegistration] = useState<ServiceWorkerRegistration | null>(null);

  useEffect(() => {
    const init = async () => {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        setIsSupported(false);
        setPermission('unsupported');
        return;
      }

      setIsSupported(true);

      if ('Notification' in window) {
        setPermission(Notification.permission as PushPermissionState);
      } else {
        setPermission('unsupported');
      }

      try {
        const registration = await navigator.serviceWorker.register('/sw.js', {
          scope: '/',
        });
        setSwRegistration(registration);

        const subscription = await registration.pushManager.getSubscription();
        setIsSubscribed(Boolean(subscription));
      } catch (err) {
        logger.error('[Push] Service worker registration failed', err);
        setError('Failed to register service worker');
      }
    };

    void init();
  }, []);

  const checkSubscription = useCallback(async () => {
    if (!swRegistration) return;

    try {
      const subscription = await swRegistration.pushManager.getSubscription();
      setIsSubscribed(Boolean(subscription));
    } catch (err) {
      logger.error('[Push] Failed to check subscription', err);
    }
  }, [swRegistration]);

  const subscribe = useCallback(async (): Promise<boolean> => {
    if (!isSupported || !swRegistration || !isAuthenticated) {
      setError('Push notifications not available');
      return false;
    }

    if (!('Notification' in window)) {
      setError('Push notifications are not supported');
      return false;
    }

    setIsLoading(true);
    setError(null);

    try {
      if (Notification.permission === 'default') {
        const result = await Notification.requestPermission();
        setPermission(result as PushPermissionState);

        if (result !== 'granted') {
          setError('Notification permission denied');
          return false;
        }
      } else if (Notification.permission === 'denied') {
        setPermission('denied');
        setError('Notification permission was denied. Please enable it in browser settings.');
        return false;
      }

      const vapidPublicKey = await pushNotificationApi.getVapidPublicKey();
      const applicationServerKey = urlBase64ToUint8Array(vapidPublicKey);

      const subscription = await swRegistration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey.buffer as ArrayBuffer,
      });

      const p256dh = arrayBufferToBase64(subscription.getKey('p256dh'));
      const auth = arrayBufferToBase64(subscription.getKey('auth'));

      await pushNotificationApi.subscribe({
        endpoint: subscription.endpoint,
        p256dh,
        auth,
        user_agent: navigator.userAgent,
      });

      setIsSubscribed(true);
      return true;
    } catch (err) {
      logger.error('[Push] Subscription failed', err);
      setError(err instanceof Error ? err.message : 'Failed to subscribe');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [isSupported, swRegistration, isAuthenticated]);

  const unsubscribe = useCallback(async (): Promise<boolean> => {
    if (!swRegistration) {
      setError('Push notifications not available');
      return false;
    }

    setIsLoading(true);
    setError(null);

    try {
      const subscription = await swRegistration.pushManager.getSubscription();

      if (subscription) {
        await subscription.unsubscribe();

        try {
          await pushNotificationApi.unsubscribe(subscription.endpoint);
        } catch (err) {
          logger.warn('[Push] Backend unsubscribe failed', err);
        }
      }

      setIsSubscribed(false);
      return true;
    } catch (err) {
      logger.error('[Push] Unsubscribe failed', err);
      setError(err instanceof Error ? err.message : 'Failed to unsubscribe');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [swRegistration]);

  return {
    isSupported,
    permission,
    isSubscribed,
    isLoading,
    error,
    subscribe,
    unsubscribe,
    checkSubscription,
  };
}
