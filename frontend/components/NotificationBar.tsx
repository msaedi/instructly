// frontend/components/NotificationBar.tsx
'use client';

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useAuth } from '@/features/shared/hooks/useAuth';

interface NotificationMessage {
  id: string;
  type: 'credits' | 'new_instructors' | 'deals' | 'announcement';
  message: string;
  priority: number;
}

export function NotificationBar() {
  const { user, isAuthenticated } = useAuth();
  const [dismissedMap, setDismissedMap] = useState<Record<string, number>>(() => {
    if (typeof window === 'undefined') return {};
    try {
      return JSON.parse(sessionStorage.getItem('dismissedNotifications') || '{}');
    } catch {
      return {};
    }
  });

  const [nowMs, setNowMs] = useState<number | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setNowMs(Date.now()), 0);
    return () => clearTimeout(timer);
  }, [isAuthenticated, user?.created_at, dismissedMap]);

  const notifications: NotificationMessage[] = [];
  if (isAuthenticated) {

    if (user?.credits_balance && user.credits_balance > 0) {
      notifications.push({
        id: 'credits',
        type: 'credits',
        message: `You have $${user.credits_balance} in credits! Book your next lesson today.`,
        priority: 1,
      });
    }

    const isNewUser =
      user?.created_at &&
      typeof nowMs === 'number' &&
      new Date(user.created_at).getTime() > nowMs - 7 * 24 * 60 * 60 * 1000;

    if (isNewUser) {
      notifications.push({
        id: 'welcome',
        type: 'announcement',
        message:
          'Welcome to iNSTAiNSTRU! Browse our verified instructors and book your first lesson.',
        priority: 2,
      });
    }

    notifications.push({
      id: 'new_instructors',
      type: 'new_instructors',
      message: 'New Martial Arts instructors in your area! Book today!',
      priority: 3,
    });

    notifications.push({
      id: 'deals',
      type: 'deals',
      message: '20% off Piano lessons this week - based on your searches',
      priority: 4,
    });

  }

  const currentNotification = (() => {
    if (!notifications.length) return null;
    const sorted = [...notifications].sort((a, b) => a.priority - b.priority);
    return sorted[0] ?? null;
  })();

  const isDismissed = (() => {
    if (!currentNotification) return false;
    const dismissedTime = dismissedMap[currentNotification.id];
    return (
      typeof dismissedTime === 'number' &&
      typeof nowMs === 'number' &&
      nowMs - dismissedTime < 24 * 60 * 60 * 1000
    );
  })();

  const handleDismiss = () => {
    // Store dismissal in sessionStorage to prevent reappearing
    if (currentNotification) {
      const timestamp = Date.now();
      setDismissedMap((prev) => {
        const next = { ...prev, [currentNotification.id]: timestamp };
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('dismissedNotifications', JSON.stringify(next));
        }
        return next;
      });
    }
  };

  if (!isAuthenticated || !currentNotification || isDismissed) {
    return null;
  }


  return (
    <div className="bg-gray-50 dark:bg-gray-900/20 animate-slide-down">
      <div className="w-full">
        <div className="flex items-center justify-between py-2 px-8">
          <div className="flex items-center pl-4">
            <p className="text-sm font-bold text-gray-600 dark:text-gray-400">
              {currentNotification.message}
            </p>
          </div>
          <button
            onClick={handleDismiss}
            className="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-gray-800/30 transition-colors mr-4"
            aria-label="Dismiss notification"
          >
            <X className="h-4 w-4 text-gray-600 dark:text-gray-400" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
