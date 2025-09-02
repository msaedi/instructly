// frontend/components/NotificationBar.tsx
'use client';

import { useState, useEffect } from 'react';
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
  const [currentNotification, setCurrentNotification] = useState<NotificationMessage | null>(null);
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    if (!isAuthenticated || isDismissed) return;

    // Generate notifications based on user state
    const notifications: NotificationMessage[] = [];

    // Credits notification
    if (user?.credits_balance && user.credits_balance > 0) {
      notifications.push({
        id: 'credits',
        type: 'credits',
        message: `You have $${user.credits_balance} in credits! Book your next lesson today.`,
        priority: 1,
      });
    }

    // New user welcome
    const isNewUser =
      user?.created_at &&
      new Date(user.created_at).getTime() > Date.now() - 7 * 24 * 60 * 60 * 1000;

    if (isNewUser) {
      notifications.push({
        id: 'welcome',
        type: 'announcement',
        message:
          'Welcome to InstaInstru! Browse our verified instructors and book your first lesson.',
        priority: 2,
      });
    }

    // Sample notifications (would come from API in production)
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

    // Select highest priority notification
    if (notifications.length > 0) {
      const sorted = notifications.sort((a, b) => a.priority - b.priority);
      setCurrentNotification(sorted[0]);
    }
  }, [isAuthenticated, user, isDismissed]);

  const handleDismiss = () => {
    setIsDismissed(true);

    // Store dismissal in sessionStorage to prevent reappearing
    if (currentNotification) {
      const dismissed = JSON.parse(sessionStorage.getItem('dismissedNotifications') || '{}');
      dismissed[currentNotification.id] = Date.now();
      sessionStorage.setItem('dismissedNotifications', JSON.stringify(dismissed));
    }
  };

  // Check if notification was recently dismissed
  useEffect(() => {
    if (currentNotification) {
      const dismissed = JSON.parse(sessionStorage.getItem('dismissedNotifications') || '{}');
      const dismissedTime = dismissed[currentNotification.id];

      // Hide if dismissed within last 24 hours
      if (dismissedTime && Date.now() - dismissedTime < 24 * 60 * 60 * 1000) {
        setIsDismissed(true);
      }
    }
  }, [currentNotification]);

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
            <X className="h-4 w-4 text-gray-600 dark:text-gray-400" />
          </button>
        </div>
      </div>
    </div>
  );
}
