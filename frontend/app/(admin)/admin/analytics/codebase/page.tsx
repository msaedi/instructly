'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useCodebaseMetrics } from '@/hooks/useCodebaseMetrics';
import type { CodebaseCategoryStats } from '@/lib/analyticsApi';
import { AnalyticsNav } from '../AnalyticsNav';
import { RefreshCw, GitBranch, FileCode2, Layers } from 'lucide-react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

export default function CodebaseMetricsPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAdmin } = useAdminAuth();

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const { logout } = useAuth();
  const { data, history, loading, error, refetch } = useCodebaseMetrics(token);

  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.push(`/login?redirect=${encodeURIComponent('/admin/analytics/codebase')}`);
    }
  }, [authLoading, isAdmin, router]);

  if (authLoading || (!isAdmin && !authLoading)) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <a href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">
                iNSTAiNSTRU
              </a>
              <h1 className="text-xl font-semibold">Codebase Analytics</h1>
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
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Tabs */}
        <div className="mb-6">
          <AnalyticsNav />
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {/* Summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white/60 dark:bg-gray-900/40 backdrop-blur rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6">
            <div className="flex items-center gap-3 text-gray-700 dark:text-gray-300">
              <FileCode2 className="h-5 w-5 text-indigo-600" />
              <span className="text-sm">Total Files</span>
            </div>
            <div className="mt-3 text-2xl font-semibold text-gray-900 dark:text-gray-100">
              {data?.summary.total_files?.toLocaleString() ?? '—'}
            </div>
          </div>
          <div className="bg-white/60 dark:bg-gray-900/40 backdrop-blur rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6">
            <div className="flex items-center gap-3 text-gray-700 dark:text-gray-300">
              <Layers className="h-5 w-5 text-green-600" />
              <span className="text-sm">Total Lines</span>
            </div>
            <div className="mt-3 text-2xl font-semibold text-gray-900 dark:text-gray-100">
              {data?.summary.total_lines?.toLocaleString() ?? '—'}
            </div>
          </div>
          <div className="bg-white/60 dark:bg-gray-900/40 backdrop-blur rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6">
            <div className="flex items-center gap-3 text-gray-700 dark:text-gray-300">
              <GitBranch className="h-5 w-5 text-rose-600" />
              <span className="text-sm">Total Commits</span>
            </div>
            <div className="mt-3 text-2xl font-semibold text-gray-900 dark:text-gray-100">
              {data?.git.total_commits?.toLocaleString() ?? '—'}
            </div>
          </div>
        </div>

        {/* Two column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Backend panel */}
          <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Backend (Python)</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Files: {data?.backend.total_files?.toLocaleString() ?? '—'} • Lines: {data?.backend.total_lines?.toLocaleString() ?? '—'}
            </p>

            {/* Category breakdown */}
            <div className="space-y-3">
              {data &&
                (Object.entries(data.backend.categories || {}) as [
                  string,
                  CodebaseCategoryStats
                ][]).map(([name, stats]) => (
                  <div key={name} className="flex items-center gap-3">
                    <div className="w-40 shrink-0 text-sm text-gray-700 dark:text-gray-300">{name}</div>
                    <div className="flex-1 h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                      <div
                        className="h-full bg-indigo-500"
                        style={{ width: `${Math.min(100, (stats.lines / Math.max(1, data.backend.total_lines)) * 100).toFixed(2)}%` }}
                      />
                    </div>
                    <div className="w-36 text-right text-xs text-gray-600 dark:text-gray-400">
                      {stats.files.toLocaleString()} files • {stats.lines.toLocaleString()} lines
                    </div>
                  </div>
                ))}
            </div>

            {/* Largest files */}
            <div className="mt-6">
              <h4 className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-2">Largest files</h4>
              <div className="divide-y divide-gray-200/60 dark:divide-gray-800/60 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/50 dark:bg-gray-900/30">
                {(data?.backend.largest_files || []).slice(0, 5).map((f: { path: string; lines: number }, idx: number) => (
                  <div key={idx} className="p-3 flex items-center justify-between text-sm">
                    <div className="truncate pr-4 text-gray-700 dark:text-gray-300">{f.path}</div>
                    <div className="text-gray-600 dark:text-gray-400">{f.lines.toLocaleString()} lines</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Frontend panel */}
          <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Frontend (TS/JS)</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Files: {data?.frontend.total_files?.toLocaleString() ?? '—'} • Lines: {data?.frontend.total_lines?.toLocaleString() ?? '—'}
            </p>

            {/* Category breakdown */}
            <div className="space-y-3">
              {data &&
                (Object.entries(data.frontend.categories || {}) as [
                  string,
                  CodebaseCategoryStats
                ][]).map(([name, stats]) => (
                  <div key={name} className="flex items-center gap-3">
                    <div className="w-40 shrink-0 text-sm text-gray-700 dark:text-gray-300">{name}</div>
                    <div className="flex-1 h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                      <div
                        className="h-full bg-emerald-500"
                        style={{ width: `${Math.min(100, (stats.lines / Math.max(1, data.frontend.total_lines)) * 100).toFixed(2)}%` }}
                      />
                    </div>
                    <div className="w-36 text-right text-xs text-gray-600 dark:text-gray-400">
                      {stats.files.toLocaleString()} files • {stats.lines.toLocaleString()} lines
                    </div>
                  </div>
                ))}
            </div>

            {/* Largest files */}
            <div className="mt-6">
              <h4 className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-2">Largest files</h4>
              <div className="divide-y divide-gray-200/60 dark:divide-gray-800/60 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/50 dark:bg-gray-900/30">
                {(data?.frontend.largest_files || []).slice(0, 5).map((f: { path: string; lines: number }, idx: number) => (
                  <div key={idx} className="p-3 flex items-center justify-between text-sm">
                    <div className="truncate pr-4 text-gray-700 dark:text-gray-300">{f.path}</div>
                    <div className="text-gray-600 dark:text-gray-400">{f.lines.toLocaleString()} lines</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Git stats and meta */}
        <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Git Statistics</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <div className="p-4 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/70 dark:bg-gray-900/30">
              <div className="text-gray-500 dark:text-gray-400">Contributors</div>
              <div className="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{data?.git.unique_contributors ?? '—'}</div>
            </div>
            <div className="p-4 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/70 dark:bg-gray-900/30">
              <div className="text-gray-500 dark:text-gray-400">First commit</div>
              <div className="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{data?.git.first_commit ?? '—'}</div>
            </div>
            <div className="p-4 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/70 dark:bg-gray-900/30">
              <div className="text-gray-500 dark:text-gray-400">Last commit</div>
              <div className="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{data?.git.last_commit ?? '—'}</div>
            </div>
            <div className="p-4 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/70 dark:bg-gray-900/30">
              <div className="text-gray-500 dark:text-gray-400">Branch</div>
              <div className="mt-1 text-xl font-semibold text-gray-900 dark:text-gray-100">{data?.git.current_branch ?? '—'}</div>
            </div>
          </div>
        </div>

        {/* Trend charts */}
        <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Files chart */}
          <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Total Files Over Time</h3>
            <div className="h-64">
              {history && history.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={history.map((h) => ({
                      date: new Date(h.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                      total_files: h.total_files,
                    }))}
                  >
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
                    <Line type="monotone" dataKey="total_files" name="Files" stroke="#0ea5e9" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500 dark:text-gray-400">
                  No history available yet.
                </div>
              )}
            </div>
          </div>

          {/* Lines chart */}
          <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Total Lines Over Time</h3>
            <div className="h-64">
              {history && history.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={history.map((h) => ({
                      date: new Date(h.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                      total_lines: h.total_lines,
                      backend_lines: h.backend_lines,
                      frontend_lines: h.frontend_lines,
                    }))}
                  >
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
                    <Line type="monotone" dataKey="total_lines" name="Total" stroke="#4f46e5" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="backend_lines" name="Backend" stroke="#059669" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="frontend_lines" name="Frontend" stroke="#f59e0b" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500 dark:text-gray-400">
                  No history available yet.
                </div>
              )}
            </div>
          </div>

          {/* Commits chart */}
          <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Total Commits Over Time</h3>
            <div className="h-64">
              {history && history.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={history.map((h) => ({
                      date: new Date(h.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                      commits: h.git_commits,
                    }))}
                  >
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
                    <Line type="monotone" dataKey="commits" name="Commits" stroke="#ef4444" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500 dark:text-gray-400">
                  No history available yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
