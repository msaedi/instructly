// frontend/app/(admin)/admin/analytics/search/components/SearchTypesChart.tsx
'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import type { SearchAnalyticsSummary } from '@/lib/analyticsApi';

interface SearchTypesChartProps {
  summary: SearchAnalyticsSummary | null;
  loading: boolean;
}

const COLORS = {
  natural_language: '#3b82f6',
  service_pill: '#10b981',
  category: '#f59e0b',
  filter: '#8b5cf6',
  search_history: '#ef4444',
};

const TYPE_LABELS = {
  natural_language: 'Natural Language',
  service_pill: 'Service Pills',
  category: 'Categories',
  filter: 'Filters',
  search_history: 'Search History',
};

export function SearchTypesChart({ summary, loading }: SearchTypesChartProps) {
  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32 mb-4"></div>
          <div className="h-64 bg-gray-100 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  if (!summary?.search_types) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Search Types
        </h3>
        <div className="h-64 flex items-center justify-center text-gray-500 dark:text-gray-400">
          No data available
        </div>
      </div>
    );
  }

  // Convert search types to chart data
  const chartData = Object.entries(summary.search_types).map(([type, data]) => ({
    name: TYPE_LABELS[type as keyof typeof TYPE_LABELS] || type,
    value: data.count,
    percentage: data.percentage,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white dark:bg-gray-800 p-3 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
          <p className="font-medium text-gray-900 dark:text-gray-100">{payload[0].name}</p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Count: {payload[0].value.toLocaleString()}
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {payload[0].payload.percentage.toFixed(1)}%
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
        Search Types Distribution
      </h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              labelLine={false}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
              label={({ percentage }) => `${percentage.toFixed(0)}%`}
            >
              {chartData.map((entry, index) => {
                const type = Object.keys(TYPE_LABELS).find(
                  (key) => TYPE_LABELS[key as keyof typeof TYPE_LABELS] === entry.name
                );
                const color = type ? COLORS[type as keyof typeof COLORS] : '#6b7280';
                return <Cell key={`cell-${index}`} fill={color} />;
              })}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
