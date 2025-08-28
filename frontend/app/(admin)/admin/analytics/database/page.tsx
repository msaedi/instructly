'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useDatabaseData } from '@/hooks/useDatabaseData';
import { RefreshCw, Database, AlertCircle } from 'lucide-react';
import DatabasePoolStatus from './components/DatabasePoolStatus';
import { AnalyticsNav } from '../AnalyticsNav';
import { useAuth } from '@/features/shared/hooks/useAuth';

export default function DatabaseAnalyticsPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAdmin } = useAdminAuth();
  const { logout } = useAuth();

  // Get token from localStorage
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const { data, loading: dataLoading, error, refetch } = useDatabaseData(token);

  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.push(`/login?redirect=${encodeURIComponent('/admin/analytics/database')}`);
    }
  }, [authLoading, isAdmin, router]);

  if (authLoading || (!isAdmin && !authLoading)) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  const loading = authLoading || dataLoading;

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
              <h1 className="text-xl font-semibold">Database Analytics</h1>
            </div>
            <div className="flex items-center space-x-3">
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
        {/* Navigation */}
        <div className="mb-6">
          <AnalyticsNav />
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

      {/* Connection Pool Status - CRITICAL FOR PRODUCTION */}
      <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="p-6 border-b border-gray-200/70 dark:border-gray-700/60">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Database className="h-5 w-5" />
            Connection Pool Status
          </h3>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="h-64 bg-gray-100 dark:bg-gray-700 rounded animate-pulse"></div>
          ) : (
            <DatabasePoolStatus pool={data?.pool} />
          )}
        </div>
      </div>

        {/* Production Alert */}
        {data?.pool && data.pool.usage_percent > 80 && (
          <div className="mt-6 p-4 bg-red-50/80 dark:bg-red-900/20 ring-1 ring-red-200/70 dark:ring-red-800/60 rounded-xl">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-red-600" />
              <div>
                <p className="font-medium text-red-800 dark:text-red-300">Production Alert</p>
                <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                  Database connection pool is at {data.pool.usage_percent}% capacity. Deploy the
                  increased pool size configuration immediately.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Auto-refresh indicator */}
        <div className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
          <Database className="inline-block h-4 w-4 mr-1" />
          Auto-refreshing every 30 seconds
        </div>
      </main>
    </div>
  );
}
