'use client';

import { Bell, Calendar, Gift, MessageSquare, Star } from 'lucide-react';
import { cn } from '@/lib/utils';

const CATEGORY_STYLES: Record<string, { icon: typeof Bell; className: string }> = {
  lesson_updates: {
    icon: Calendar,
    className: 'bg-purple-50 text-[#7E22CE]',
  },
  messages: {
    icon: MessageSquare,
    className: 'bg-blue-50 text-blue-600',
  },
  reviews: {
    icon: Star,
    className: 'bg-emerald-50 text-emerald-600',
  },
  promotional: {
    icon: Gift,
    className: 'bg-amber-50 text-amber-600',
  },
};

export function NotificationIcon({ category }: { category: string }) {
  const config = CATEGORY_STYLES[category] ?? {
    icon: Bell,
    className: 'bg-gray-100 text-gray-600',
  };
  const Icon = config.icon;

  return (
    <span className={cn('flex h-9 w-9 items-center justify-center rounded-full', config.className)}>
      <Icon className="h-4 w-4" aria-hidden="true" />
    </span>
  );
}
