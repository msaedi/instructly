'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useRedisData } from '@/hooks/useRedisData';
import { RefreshCw, Server, Activity, Database, Users } from 'lucide-react';
import StatusCards from './components/StatusCards';
import MemoryUsageChart from './components/MemoryUsageChart';
import CeleryQueuesChart from './components/CeleryQueuesChart';
import OperationsMetrics from './components/OperationsMetrics';
import { AnalyticsNav } from '../AnalyticsNav';

export default function RedisAnalyticsPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAdmin } = useAdminAuth();

  // Get token from localStorage
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const { data, loading: dataLoading, error, refetch } = useRedisData(token);

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
          <h1 className="text-3xl font-bold mb-2">Redis Analytics</h1>
          <p className="text-gray-600 dark:text-gray-400">
            Monitor Redis performance and Celery queue status
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

      {/* Connection Status Cards */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6"
            >
              <div className="animate-pulse">
                <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24 mb-2"></div>
                <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-32"></div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <StatusCards data={data} />
      )}

      {/* Main Dashboard Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Memory Usage */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-lg font-semibold flex items-center gap-2 text-gray-900 dark:text-gray-100">
              <Database className="h-5 w-5" />
              Memory Usage
            </h3>
          </div>
          <div className="p-6">
            {loading ? (
              <div className="h-64 bg-gray-100 dark:bg-gray-700 rounded animate-pulse"></div>
            ) : (
              <MemoryUsageChart stats={data.stats} />
            )}
          </div>
        </div>

        {/* Operations Metrics */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-lg font-semibold flex items-center gap-2 text-gray-900 dark:text-gray-100">
              <Activity className="h-5 w-5" />
              Operations Metrics
            </h3>
          </div>
          <div className="p-6">
            {loading ? (
              <div className="h-64 bg-gray-100 dark:bg-gray-700 rounded animate-pulse"></div>
            ) : (
              <OperationsMetrics stats={data.stats} />
            )}
          </div>
        </div>
      </div>

      {/* Celery Queues */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold flex items-center gap-2 text-gray-900 dark:text-gray-100">
            <Server className="h-5 w-5" />
            Celery Queue Status
          </h3>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="h-80 bg-gray-100 dark:bg-gray-700 rounded animate-pulse"></div>
          ) : (
            <CeleryQueuesChart queues={data.queues} />
          )}
        </div>
      </div>

      {/* Migration Progress */}
      {data.stats && data.stats.operations && (
        <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Migration Progress
            </h3>
          </div>
          <div className="p-6">
            <div className="space-y-4">
              <div>
                <div className="flex justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Daily Operations Target
                  </span>
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    {(data.stats.operations.estimated_daily_ops || 0).toLocaleString()} / 100,000
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      (data.stats.operations.estimated_daily_ops || 0) < 100000
                        ? 'bg-green-600'
                        : 'bg-red-600'
                    }`}
                    style={{
                      width: `${Math.min(
                        ((data.stats.operations.estimated_daily_ops || 0) / 100000) * 100,
                        100
                      )}%`,
                    }}
                  />
                </div>
              </div>
              <div className="text-sm">
                {(data.stats.operations.estimated_daily_ops || 0) < 100000 ? (
                  <span className="text-green-600 dark:text-green-400">
                    ✓ Redis operations optimized - using{' '}
                    {(((data.stats.operations.estimated_daily_ops || 0) / 100000) * 100).toFixed(1)}
                    % of target
                  </span>
                ) : (
                  <span className="text-red-600 dark:text-red-400">
                    ⚠️ Redis operations exceed target by{' '}
                    {(
                      (((data.stats.operations.estimated_daily_ops || 0) - 100000) / 100000) *
                      100
                    ).toFixed(1)}
                    %
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Auto-refresh indicator */}
      <div className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
        <Users className="inline-block h-4 w-4 mr-1" />
        Auto-refreshing every 30 seconds
      </div>
    </div>
  );
}
