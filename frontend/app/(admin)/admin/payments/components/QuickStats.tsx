import { AlertTriangle, BadgeDollarSign, BarChart3 } from 'lucide-react';

import type { BookingStats } from '../hooks/useBookingStats';
import { formatCurrency } from '../utils';

interface QuickStatsProps {
  stats: BookingStats | undefined;
  isLoading: boolean;
}

export default function QuickStats({ stats, isLoading }: QuickStatsProps) {
  const items = [
    {
      label: 'Today',
      icon: BarChart3,
      primary: stats ? `${stats.today.booking_count} bookings` : '--',
      secondary: stats ? `${formatCurrency(stats.today.revenue)} revenue` : '--',
    },
    {
      label: 'This Week',
      icon: BadgeDollarSign,
      primary: stats ? `${formatCurrency(stats.this_week.gmv)} GMV` : '--',
      secondary: stats ? `${formatCurrency(stats.this_week.platform_revenue)} platform` : '--',
    },
    {
      label: 'Needs Action',
      icon: AlertTriangle,
      primary: stats ? `${stats.needs_action.pending_completion} pending` : '--',
      secondary: stats ? `${stats.needs_action.disputed} disputes` : '--',
    },
  ];

  return (
    <div className="rounded-2xl p-6 bg-white/70 dark:bg-gray-900/50 ring-1 ring-gray-200/70 dark:ring-gray-700/60 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Quick Stats</h2>
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {isLoading ? 'Loading...' : 'Updated just now'}
        </span>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="rounded-xl p-4 bg-white/80 dark:bg-gray-900/60 ring-1 ring-gray-200/70 dark:ring-gray-700/60"
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-600 dark:text-gray-400">{item.label}</p>
                <Icon className="h-4 w-4 text-indigo-500" />
              </div>
              <p className="mt-3 text-lg font-semibold text-gray-900 dark:text-gray-100">{item.primary}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">{item.secondary}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
