// frontend/app/(admin)/admin/analytics/search/components/SearchTrendsChart.tsx
'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { SearchTrend } from '@/lib/analyticsApi';

interface SearchTrendsChartProps {
  data: SearchTrend[] | null;
  loading: boolean;
}

export function SearchTrendsChart({ data, loading }: SearchTrendsChartProps) {
  if (loading) {
    return (
      <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32 mb-4"></div>
          <div className="h-64 bg-gray-100 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Search Trends
        </h3>
        <div className="h-64 flex items-center justify-center text-gray-500 dark:text-gray-400">
          No data available
        </div>
      </div>
    );
  }

  // Format data for chart
  const chartData = data.map((item) => ({
    date: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    searches: item.total_searches,
    users: item.unique_users,
    guests: item.unique_guests || 0,
  }));

  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Search Trends</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
            <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#ffffff',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
              }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="searches"
              stroke="#3b82f6"
              strokeWidth={2}
              name="Total Searches"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="users"
              stroke="#10b981"
              strokeWidth={2}
              name="Unique Users"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="guests"
              stroke="#f59e0b"
              strokeWidth={2}
              name="Guest Users"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
