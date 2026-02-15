'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { withApiBase } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import type { AdminReferralsHealth, AdminReferralsSummary } from '@/features/shared/api/types';
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Server,
  ShieldAlert,
  Users,
} from 'lucide-react';

const numberFormatter = new Intl.NumberFormat('en-US');
const LAST_RUN_WARNING_SECONDS = 1800;

function formatLastRunAge(ageInSeconds: number | null): string {
  if (ageInSeconds === null) {
    return 'unknown';
  }

  if (ageInSeconds < 0) {
    return 'just now';
  }

  const hours = Math.floor(ageInSeconds / 3600);
  const minutes = Math.floor((ageInSeconds % 3600) / 60);
  const seconds = ageInSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m ago`;
  }

  if (minutes > 0) {
    return `${minutes}m ${seconds}s ago`;
  }

  return `${seconds}s ago`;
}

export default function ReferralsAdminClient() {
  const { isAdmin, isLoading } = useAdminAuth();
  const { logout } = useAuth();

  const [health, setHealth] = useState<AdminReferralsHealth | null>(null);
  const [summary, setSummary] = useState<AdminReferralsSummary | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refreshControllerRef = useRef<AbortController | null>(null);

  const healthEndpoint = useMemo(() => withApiBase('/api/v1/admin/referrals/health'), []);
  const summaryEndpoint = useMemo(() => withApiBase('/api/v1/admin/referrals/summary'), []);

  const fetchData = useCallback(
    async ({ silent = false, signal }: { silent?: boolean; signal?: AbortSignal }) => {
      const buildRequestInit = (sig?: AbortSignal): RequestInit => {
        const init: RequestInit = { credentials: 'include' };
        if (sig) {
          init.signal = sig;
        }
        return init;
      };

      if (signal?.aborted) {
        return;
      }

      if (silent) {
        setRefreshing(true);
      } else {
        setLoadingData(true);
      }

      try {
        const [healthRes, summaryRes] = await Promise.all([
          fetchWithSessionRefresh(healthEndpoint, buildRequestInit(signal)),
          fetchWithSessionRefresh(summaryEndpoint, buildRequestInit(signal)),
        ]);

        if (signal?.aborted) {
          return;
        }

        if (!healthRes.ok) {
          throw new Error(`health request failed (${healthRes.status})`);
        }
        if (!summaryRes.ok) {
          throw new Error(`summary request failed (${summaryRes.status})`);
        }

        const [healthJson, summaryJson] = await Promise.all([healthRes.json(), summaryRes.json()]);

        if (signal?.aborted) {
          return;
        }

        setHealth(healthJson as AdminReferralsHealth);
        setSummary(summaryJson as AdminReferralsSummary);
        setError(null);
      } catch (err) {
        if (signal?.aborted) {
          return;
        }
        const message = err instanceof Error ? err.message : 'Failed to load referrals data';
        setError(message);
        setHealth(null);
        setSummary(null);
      } finally {
        if (signal?.aborted) {
          return;
        }
        if (silent) {
          setRefreshing(false);
        } else {
          setLoadingData(false);
        }
      }
    },
    [healthEndpoint, summaryEndpoint],
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetchData({ silent: false, signal: controller.signal });
    return () => controller.abort();
  }, [fetchData]);

  useEffect(() => () => {
    if (refreshControllerRef.current) {
      refreshControllerRef.current.abort();
      refreshControllerRef.current = null;
    }
  }, []);

  const counts = useMemo(() => summary?.counts_by_status ?? {}, [summary?.counts_by_status]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <Loader2 className="h-10 w-10 animate-spin text-indigo-500" aria-label="Loading" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
        <div className="max-w-md rounded-xl border border-gray-200/70 dark:border-gray-800 bg-white/70 dark:bg-gray-900/60 backdrop-blur p-6 text-center">
          <ShieldAlert className="h-10 w-10 mx-auto text-amber-500" aria-hidden="true" />
          <p className="mt-3 text-sm text-gray-700 dark:text-gray-300">You do not have access to this page.</p>
        </div>
      </div>
    );
  }

  const workersAlive = health?.workers_alive ?? 0;
  const backlogDue = health?.backlog_pending_due ?? 0;
  const pendingTotal = health?.pending_total ?? 0;
  const unlockedTotal = health?.unlocked_total ?? 0;
  const voidTotal = health?.void_total ?? 0;
  const lastRunAgeSeconds = health?.last_run_age_s ?? null;
  const lastRunIsStale = lastRunAgeSeconds !== null && lastRunAgeSeconds > LAST_RUN_WARNING_SECONDS;
  const lastRunDisplay = formatLastRunAge(lastRunAgeSeconds);
  const clicks24h = summary?.clicks_24h ?? 0;
  const attributions24h = summary?.attributions_24h ?? 0;

  const isFetching = loadingData || refreshing;

  const handleRefresh = () => {
    if (refreshControllerRef.current) {
      refreshControllerRef.current.abort();
    }
    const controller = new AbortController();
    refreshControllerRef.current = controller;
    const refreshPromise = fetchData({ silent: true, signal: controller.signal });
    void refreshPromise.finally(() => {
      if (refreshControllerRef.current === controller) {
        refreshControllerRef.current = null;
      }
    });
  };

  const workerCardClasses = workersAlive > 0
    ? 'bg-white/60 dark:bg-gray-900/40 ring-emerald-200/70 dark:ring-emerald-800/50 text-gray-900 dark:text-gray-100'
    : 'bg-rose-50 dark:bg-rose-900/20 ring-rose-200/60 dark:ring-rose-800/60 text-rose-900 dark:text-rose-100';

  const backlogCardClasses = backlogDue > 0
    ? 'bg-amber-50 dark:bg-amber-900/20 ring-amber-200/60 dark:ring-amber-800/50 text-amber-900 dark:text-amber-100'
    : 'bg-white/60 dark:bg-gray-900/40 ring-gray-200/70 dark:ring-gray-700/60 text-gray-900 dark:text-gray-100';
  const backlogChipClasses = backlogDue > 0
    ? 'bg-amber-500/15 text-amber-700 dark:text-amber-200'
    : 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-200';
  const lastRunTextClasses = lastRunIsStale
    ? 'text-amber-600 dark:text-amber-300'
    : 'text-gray-700 dark:text-gray-300';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">
                iNSTAiNSTRU
              </Link>
              <div>
                <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Referrals Admin</h1>
                <p className="text-sm text-gray-600 dark:text-gray-400">Unlocker health, backlog, and top referrers.</p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={() => handleRefresh()}
                disabled={isFetching}
                className="inline-flex items-center justify-center h-9 w-9 rounded-full text-indigo-600 hover:text-white hover:bg-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/70 disabled:opacity-50"
                aria-label="Refresh data"
                title="Refresh data"
              >
                <RefreshCw className={`h-5 w-5 ${isFetching ? 'animate-spin' : ''}`} />
              </button>
              <button
                type="button"
                onClick={() => void logout()}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60"
                aria-label="Log out"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>

          <section className="col-span-12 md:col-span-9 lg:col-span-9 space-y-6">
            {error && (
              <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-2xl text-sm text-red-700 dark:text-red-300 flex items-start gap-3">
                <AlertCircle className="h-5 w-5 mt-0.5" aria-hidden="true" />
                <div>
                  <p className="font-semibold">Failed to load referrals metrics</p>
                  <p>{error}</p>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className={`rounded-2xl p-6 shadow-sm ring-1 backdrop-blur ${workerCardClasses}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Workers Alive</p>
                    <p className="mt-3 text-3xl font-semibold">{numberFormatter.format(workersAlive)}</p>
                  </div>
                  <Server className="h-10 w-10 opacity-80" aria-hidden="true" />
                </div>
                <p className="mt-4 text-xs">
                  {health?.workers?.length ? health.workers.join(', ') : 'No workers responding'}
                </p>
                <p className={`mt-3 text-xs font-medium ${lastRunTextClasses}`}>Last run: {lastRunDisplay}</p>
              </div>

              <div className={`rounded-2xl p-6 shadow-sm ring-1 backdrop-blur ${backlogCardClasses}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Backlog Pending Due</p>
                    <p className="mt-3 text-3xl font-semibold">{numberFormatter.format(backlogDue)}</p>
                  </div>
                  <AlertCircle className="h-10 w-10 opacity-80" aria-hidden="true" />
                </div>
                <p className="mt-4 text-xs text-gray-700 dark:text-gray-300">
                  Rewards pending unlock with past-due unlock timestamps.
                </p>
                <span
                  className={`mt-3 inline-flex w-fit items-center rounded-full px-3 py-1 text-xs font-semibold ${backlogChipClasses}`}
                >
                  {backlogDue > 0 ? 'Attention required' : 'No backlog'}
                </span>
              </div>

              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Reward Totals</p>
                <dl className="mt-4 grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <dt className="text-gray-500 dark:text-gray-400">Pending</dt>
                    <dd className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {numberFormatter.format(pendingTotal)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500 dark:text-gray-400">Unlocked</dt>
                    <dd className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {numberFormatter.format(unlockedTotal)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500 dark:text-gray-400">Void</dt>
                    <dd className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {numberFormatter.format(voidTotal)}
                    </dd>
                  </div>
                </dl>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">24h Signals</h2>
                <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                  <div className="flex items-center gap-3">
                    <Users className="h-5 w-5 text-indigo-500" aria-hidden="true" />
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">Clicks</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {numberFormatter.format(clicks24h)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden="true" />
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">Attributions</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        {numberFormatter.format(attributions24h)}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
                <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Status Breakdown</h2>
                <ul className="mt-4 space-y-2 text-sm">
                  {['pending', 'unlocked', 'redeemed', 'void'].map((key) => (
                    <li key={key} className="flex items-center justify-between">
                      <span className="capitalize text-gray-600 dark:text-gray-400">{key}</span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">
                        {numberFormatter.format(counts[key] ?? 0)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200/70 dark:border-gray-800/60">
                <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Top Referrers (20)</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-900/60">
                    <tr>
                      <th scope="col" className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                        User ID
                      </th>
                      <th scope="col" className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                        Rewards
                      </th>
                      <th scope="col" className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                        Code
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                    {(summary?.top_referrers ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-6 py-4 text-center text-gray-500 dark:text-gray-400">
                          No referrers recorded.
                        </td>
                      </tr>
                    ) : (
                      summary!.top_referrers.map((entry) => (
                        <tr key={`${entry.user_id}-${entry.code ?? 'no-code'}`}>
                          <td className="px-6 py-3 font-mono text-xs text-indigo-600 dark:text-indigo-300">{entry.user_id}</td>
                          <td className="px-6 py-3">{numberFormatter.format(entry.count)}</td>
                          <td className="px-6 py-3 text-gray-600 dark:text-gray-300">{entry.code ?? '—'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {isFetching && (
              <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Updating data…
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
