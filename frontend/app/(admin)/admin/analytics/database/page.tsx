'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useDatabaseData } from '@/hooks/useDatabaseData';
import { RefreshCw, Database, AlertCircle } from 'lucide-react';
import DatabasePoolStatus from './components/DatabasePoolStatus';
import { AnalyticsNav } from '../AnalyticsNav';

export default function DatabaseAnalyticsPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAdmin } = useAdminAuth();

  // Get token from localStorage
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const { data, loading: dataLoading, error, refetch } = useDatabaseData(token);

  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.push('/admin');
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
    <div className="container mx-auto py-8 px-4">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold mb-2">Database Analytics</h1>
          <p className="text-gray-600 dark:text-gray-400">
            Monitor PostgreSQL/Supabase connection pool and performance
          </p>
        </div>
        <div className="flex gap-4">
          <button
            onClick={refetch}
            disabled={loading}
            className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

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
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold flex items-center gap-2 text-gray-900 dark:text-gray-100">
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
        <div className="mt-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
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
    </div>
  );
}
