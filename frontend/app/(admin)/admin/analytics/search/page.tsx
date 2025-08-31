// frontend/app/(admin)/admin/analytics/search/page.tsx
'use client';

import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAnalyticsData } from '@/hooks/useAnalyticsData';
import { SummaryCards } from './components/SummaryCards';
import { DateRangeSelector } from './components/DateRangeSelector';
import { SearchTrendsChart } from './components/SearchTrendsChart';
import { PopularSearchesTable } from './components/PopularSearchesTable';
import { SearchTypesChart } from './components/SearchTypesChart';
import { RefreshCw, AlertCircle } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAuth } from '@/features/shared/hooks/useAuth';

export default function SearchAnalyticsDashboard() {
  const { isAdmin, isLoading: authLoading } = useAdminAuth();
  const { logout } = useAuth();

  // Cookies-only auth; analyticsApi must be updated to use cookies server-side
  const token = null;

  const { data, loading, error, refetch, dateRange, setDateRange } = useAnalyticsData(token);

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // This will be handled by the useAdminAuth hook redirect
  if (!isAdmin) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">
                iNSTAiNSTRU
              </Link>
              <h1 className="text-xl font-semibold">
                Search Analytics Dashboard
              </h1>
            </div>
            <div className="flex items-center space-x-3">
              <DateRangeSelector value={dateRange} onChange={setDateRange} />
              <button
                onClick={refetch}
                disabled={loading}
                className="inline-flex items-center justify-center h-9 w-9 rounded-full text-indigo-600 hover:text-white hover:bg-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/70 disabled:opacity-50"
                title="Refresh data"
              >
                <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={logout}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>
          <div className="col-span-12 md:col-span-9 lg:col-span-9">

        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex items-center">
              <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-2" />
              <p className="text-red-700 dark:text-red-300">{error}</p>
            </div>
          </div>
        )}

        {/* Summary Cards */}
        <div className="mb-8">
          <SummaryCards summary={data.summary} loading={loading} />
        </div>

        {/* Key Insights */}
        {data.summary && !loading && (
          <div className="mb-8 rounded-2xl p-6 bg-gradient-to-b from-indigo-50 to-white dark:from-indigo-900/10 dark:to-transparent ring-1 ring-indigo-200/70 dark:ring-indigo-800/60">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-blue-900 dark:text-blue-100">Key Insights</h2>
              <Dialog.Root>
                <Dialog.Trigger className="inline-flex items-center rounded-full px-3 py-1.5 text-sm font-medium text-indigo-700 dark:text-indigo-300 ring-1 ring-indigo-300/70 dark:ring-indigo-700/60 hover:bg-indigo-50/70 dark:hover:bg-indigo-900/20">View details</Dialog.Trigger>
                <Dialog.Portal>
                  <Dialog.Overlay className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40" />
                  <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="pointer-events-auto w-full max-w-2xl bg-white dark:bg-gray-900 rounded-xl shadow-2xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
                      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                        <Dialog.Title className="text-base font-semibold">Insights detail</Dialog.Title>
                        <Dialog.Close className="text-sm text-gray-600 hover:underline">Close</Dialog.Close>
                      </div>
                      <div className="p-4 text-sm space-y-2">
                        <div>Most searched: {data.popularSearches?.[0]?.query ?? 'n/a'} ({data.popularSearches?.[0]?.search_count ?? 0})</div>
                        <div>Guest→User CVR: {data.summary.conversions?.guest_sessions?.conversion_rate ? (data.summary.conversions.guest_sessions.conversion_rate * 100).toFixed(1) + '%' : 'n/a'}</div>
                        <div>Zero-result rate: {data.summary.performance?.zero_result_rate ? (data.summary.performance.zero_result_rate * 100).toFixed(1) + '%' : 'n/a'}</div>
                      </div>
                    </div>
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>
            </div>
            <ul className="space-y-2 text-blue-800 dark:text-blue-200">
              {data.popularSearches && data.popularSearches.length > 0 && (
                <li>
                  • "{data.popularSearches[0].query}" is your most searched service (
                  {data.popularSearches[0].search_count} searches)
                </li>
              )}
              {data.summary.conversions?.guest_sessions?.conversion_rate && (
                <li>
                  • Guest to user conversion rate:{' '}
                  {(data.summary.conversions.guest_sessions.conversion_rate * 100).toFixed(1)}%
                </li>
              )}
              {data.summary.performance?.zero_result_rate && (
                <li>
                  • {(data.summary.performance.zero_result_rate * 100).toFixed(1)}% of searches
                  return no results
                </li>
              )}
              {data.trends && data.trends.length > 1 && (
                <li>
                  • Search volume{' '}
                  {data.trends[data.trends.length - 1].total_searches >
                  data.trends[0].total_searches
                    ? 'increased'
                    : 'decreased'}{' '}
                  {Math.abs(
                    ((data.trends[data.trends.length - 1].total_searches -
                      data.trends[0].total_searches) /
                      data.trends[0].total_searches) *
                      100
                  ).toFixed(0)}
                  % over the period
                </li>
              )}
            </ul>
          </div>
        )}

        {/* Charts Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <SearchTrendsChart data={data.trends} loading={loading} />
          <SearchTypesChart summary={data.summary} loading={loading} />
        </div>

        {/* Tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <PopularSearchesTable data={data.popularSearches} loading={loading} />
          <ZeroResultsTable data={data.zeroResults} loading={loading} />
        </div>

        {/* Additional Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ReferrerAnalysis data={data.referrers} loading={loading} />
          <ServicePillPerformance data={data.servicePills} loading={loading} />
        </div>
          </div>
        </div>
      </main>
    </div>
  );
}

// Zero Results Table Component
function ZeroResultsTable({ data, loading }: { data: any[] | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-40 mb-4"></div>
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-gray-100 dark:bg-gray-700 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
        Zero Result Searches
      </h3>
      {!data || data.length === 0 ? (
        <p className="text-gray-500 dark:text-gray-400 text-center py-8">
          No zero-result searches found
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left border-b border-gray-200 dark:border-gray-700">
                <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Query</th>
                <th className="pb-3 pl-4 font-medium text-gray-700 dark:text-gray-300">Count</th>
              </tr>
            </thead>
            <tbody>
              {data.slice(0, 5).map((item, index) => (
                <tr key={index} className="border-b border-gray-100 dark:border-gray-700">
                  <td className="py-3 pr-4 text-gray-900 dark:text-gray-100">{item.query}</td>
                  <td className="py-3 pl-4 text-gray-600 dark:text-gray-400">{item.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// Referrer Analysis Component
function ReferrerAnalysis({ data, loading }: { data: any[] | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-40 mb-4"></div>
          <div className="h-32 bg-gray-100 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
        Search Referrers
      </h3>
      {!data || data.length === 0 ? (
        <p className="text-gray-500 dark:text-gray-400 text-center py-8">
          No referrer data available
        </p>
      ) : (
        <div className="space-y-3">
          {data.slice(0, 5).map((item, index) => (
            <div key={index} className="flex items-center justify-between">
              <span className="text-gray-700 dark:text-gray-300">{item.page || 'Direct'}</span>
              <div className="flex items-center space-x-3">
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {item.search_count} searches
                </span>
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {item.unique_sessions} sessions
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Service Pill Performance Component
function ServicePillPerformance({ data, loading }: { data: any[] | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-40 mb-4"></div>
          <div className="h-32 bg-gray-100 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
        Service Pill Performance
      </h3>
      {!data || data.length === 0 ? (
        <p className="text-gray-500 dark:text-gray-400 text-center py-8">
          No service pill data available
        </p>
      ) : (
        <div className="space-y-3">
          {data.slice(0, 5).map((item, index) => (
            <div key={index} className="flex items-center justify-between">
              <span className="text-gray-700 dark:text-gray-300">{item.service_name}</span>
              <div className="flex items-center space-x-3">
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {item.clicks} clicks
                </span>
                <span className="text-sm font-medium text-green-600 dark:text-green-400">
                  {(item.conversion_rate * 100).toFixed(1)}% CVR
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
