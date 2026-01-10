// Service Worker for Push Notifications
// This file must be in the public folder to be registered at the root scope

const NOTIFICATION_ICON = '/icons/icon-192x192.png';
const NOTIFICATION_BADGE = '/icons/badge-72x72.png';
const DEFAULT_TITLE = 'iNSTAiNSTRU';
const DEFAULT_BODY = 'You have a new notification';

function resolveApiBase() {
  const origin = self.location.origin;
  const hostname = self.location.hostname;
  const protocol = self.location.protocol;

  if (hostname === 'beta-local.instainstru.com') {
    return 'http://api.beta-local.instainstru.com:8000';
  }
  if (hostname === 'preview.instainstru.com') {
    return 'https://preview-api.instainstru.com';
  }
  if (hostname.endsWith('.instainstru.com')) {
    return 'https://api.instainstru.com';
  }
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `${protocol}//${hostname}:8000`;
  }

  return origin;
}

function buildApiUrl(path) {
  const base = resolveApiBase();
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

function arrayBufferToBase64(buffer) {
  if (!buffer) return '';
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

// Handle push events
self.addEventListener('push', (event) => {
  let data = {
    title: DEFAULT_TITLE,
    body: DEFAULT_BODY,
    icon: NOTIFICATION_ICON,
    badge: NOTIFICATION_BADGE,
    url: '/',
    tag: 'default',
    data: {},
  };

  if (event.data) {
    try {
      const payload = event.data.json();
      data = {
        title: payload.title || data.title,
        body: payload.body || data.body,
        icon: payload.icon || data.icon,
        badge: payload.badge || data.badge,
        url: payload.url || payload.data?.url || data.url,
        tag: payload.tag || data.tag,
        data: payload.data || {},
      };
    } catch (error) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    tag: data.tag,
    renotify: true,
    requireInteraction: false,
    data: {
      url: data.url,
      ...data.data,
    },
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

// Handle notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.focus();
          client.navigate(url);
          return;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

// Handle push subscription change (browser may rotate keys)
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil(
    self.registration.pushManager
      .subscribe({
        userVisibleOnly: true,
        applicationServerKey: event.oldSubscription?.options?.applicationServerKey,
      })
      .then((subscription) => {
        if (!subscription) return undefined;
        return fetch(buildApiUrl('/api/v1/push/subscribe'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            endpoint: subscription.endpoint,
            p256dh: arrayBufferToBase64(subscription.getKey('p256dh')),
            auth: arrayBufferToBase64(subscription.getKey('auth')),
          }),
          credentials: 'include',
        });
      })
  );
});
