// frontend/app/(admin)/admin/analytics/search/components/PopularSearchesTable.tsx
'use client';

import { useState } from 'react';
import { Search, Download } from 'lucide-react';
import type { PopularSearch } from '@/lib/analyticsApi';
import { exportToCSV } from '../utils/csvExport';

interface PopularSearchesTableProps {
  data: PopularSearch[] | null;
  loading: boolean;
}

export function PopularSearchesTable({ data, loading }: PopularSearchesTableProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortField, setSortField] = useState<keyof PopularSearch>('search_count');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-40 mb-4"></div>
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-12 bg-gray-100 dark:bg-gray-700 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Popular Searches
        </h3>
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">
          No search data available
        </div>
      </div>
    );
  }

  // Filter and sort data
  const filteredData = data.filter((item) =>
    item.query.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const sortedData = [...filteredData].sort((a, b) => {
    const aValue = a[sortField];
    const bValue = b[sortField];
    const modifier = sortDirection === 'asc' ? 1 : -1;

    if (typeof aValue === 'string' && typeof bValue === 'string') {
      return aValue.localeCompare(bValue) * modifier;
    }
    return ((aValue as number) - (bValue as number)) * modifier;
  });

  const handleSort = (field: keyof PopularSearch) => {
    if (field === sortField) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const handleExport = () => {
    exportToCSV(sortedData, 'popular-searches');
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Popular Searches</h3>
        <button
          onClick={handleExport}
          className="flex items-center space-x-2 px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        >
          <Download className="h-4 w-4" />
          <span>Export CSV</span>
        </button>
      </div>

      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search queries..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left border-b border-gray-200 dark:border-gray-700">
              <th
                className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:text-gray-900 dark:hover:text-gray-100"
                onClick={() => handleSort('query')}
              >
                Query {sortField === 'query' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th
                className="pb-3 px-4 font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:text-gray-900 dark:hover:text-gray-100"
                onClick={() => handleSort('search_count')}
              >
                Count {sortField === 'search_count' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th
                className="pb-3 px-4 font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:text-gray-900 dark:hover:text-gray-100"
                onClick={() => handleSort('unique_users')}
              >
                Unique Users {sortField === 'unique_users' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th
                className="pb-3 pl-4 font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:text-gray-900 dark:hover:text-gray-100"
                onClick={() => handleSort('average_results')}
              >
                Avg Results{' '}
                {sortField === 'average_results' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedData.slice(0, 10).map((item, index) => (
              <tr
                key={index}
                className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50"
              >
                <td className="py-3 pr-4 text-gray-900 dark:text-gray-100">{item.query}</td>
                <td className="py-3 px-4 text-gray-600 dark:text-gray-400">
                  {item.search_count.toLocaleString()}
                </td>
                <td className="py-3 px-4 text-gray-600 dark:text-gray-400">
                  {item.unique_users.toLocaleString()}
                </td>
                <td className="py-3 pl-4 text-gray-600 dark:text-gray-400">
                  <span
                    className={
                      item.average_results === 0 ? 'text-red-600 dark:text-red-400 font-medium' : ''
                    }
                  >
                    {item.average_results.toFixed(1)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
