// frontend/app/(admin)/admin/analytics/search/components/SummaryCards.tsx
'use client';

import { Search, Users, TrendingUp, AlertCircle } from 'lucide-react';
import type { SearchAnalyticsSummary } from '@/lib/analyticsApi';

interface SummaryCardsProps {
  summary: SearchAnalyticsSummary | null;
  loading: boolean;
}

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: number;
  loading?: boolean;
}

function StatCard({ title, value, subtitle, icon, trend, loading }: StatCardProps) {
  if (loading) {
    return (
      <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24 mb-2"></div>
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-32 mb-1"></div>
          <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-20"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">{title}</h3>
        <div className="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg text-indigo-600 dark:text-indigo-400">
          {icon}
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {typeof value === 'number' ? value.toLocaleString() : value}
        </p>
        {subtitle && <p className="text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>}
        {trend !== undefined && (
          <p className={`text-sm ${trend > 0 ? 'text-green-600' : 'text-red-600'}`}>
            {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}% from last period
          </p>
        )}
      </div>
    </div>
  );
}

export function SummaryCards({ summary, loading }: SummaryCardsProps) {
  const totalSearches = summary?.totals?.total_searches || 0;
  const uniqueUsers = summary?.totals?.total_users || 0;
  const guestConversion = summary?.conversions?.['guest_sessions'] as { conversion_rate?: number } | undefined;
  const conversionRate = guestConversion?.conversion_rate ?? 0;
  const zeroResultRate = summary?.performance?.zero_result_rate || 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <StatCard
        title="Total Searches"
        value={totalSearches}
        subtitle={`${summary?.date_range?.days || 30} day period`}
        icon={<Search className="h-5 w-5" />}
        loading={loading}
      />

      <StatCard
        title="Unique Users"
        value={uniqueUsers}
        subtitle={`${summary?.users?.user_percentage?.toFixed(1) || 0}% authenticated`}
        icon={<Users className="h-5 w-5" />}
        loading={loading}
      />

      <StatCard
        title="Conversion Rate"
        value={`${(conversionRate * 100).toFixed(1)}%`}
        subtitle="Guest to user"
        icon={<TrendingUp className="h-5 w-5" />}
        loading={loading}
      />

      <StatCard
        title="Zero Results"
        value={`${(zeroResultRate * 100).toFixed(1)}%`}
        subtitle="Searches with no results"
        icon={<AlertCircle className="h-5 w-5" />}
        loading={loading}
      />
    </div>
  );
}
