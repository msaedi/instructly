'use client';

import { useEffect, useMemo, useState } from 'react';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { withApiBase } from '@/lib/apiBase';
import { AlertCircle, CheckCircle2, Loader2, Server, ShieldAlert, Users } from 'lucide-react';

interface AdminReferralsHealth {
  workers_alive: number;
  workers: string[];
  backlog_pending_due: number;
  pending_total: number;
  unlocked_total: number;
  void_total: number;
}

interface AdminReferralsSummary {
  counts_by_status: Record<string, number>;
  cap_utilization_percent: number;
  top_referrers: { user_id: string; count: number; code: string | null }[];
  clicks_24h: number;
  attributions_24h: number;
}

const numberFormatter = new Intl.NumberFormat('en-US');

export default function AdminReferralsPage() {
  const { isAdmin, isLoading } = useAdminAuth();
  const [health, setHealth] = useState<AdminReferralsHealth | null>(null);
  const [summary, setSummary] = useState<AdminReferralsSummary | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        setLoadingData(true);
        const [healthRes, summaryRes] = await Promise.all([
          fetch(withApiBase('/api/admin/referrals/health'), { credentials: 'include' }),
          fetch(withApiBase('/api/admin/referrals/summary'), { credentials: 'include' }),
        ]);

        if (!healthRes.ok) {
          throw new Error(`health request failed (${healthRes.status})`);
        }
        if (!summaryRes.ok) {
          throw new Error(`summary request failed (${summaryRes.status})`);
        }

        const [healthJson, summaryJson] = await Promise.all([healthRes.json(), summaryRes.json()]);
        if (!cancelled) {
          setHealth(healthJson as AdminReferralsHealth);
          setSummary(summaryJson as AdminReferralsSummary);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Failed to load referrals data';
          setError(message);
          setHealth(null);
          setSummary(null);
        }
      } finally {
        if (!cancelled) {
          setLoadingData(false);
        }
      }
    }

    void fetchData();

    return () => {
      cancelled = true;
    };
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
  const clicks24h = summary?.clicks_24h ?? 0;
  const attributions24h = summary?.attributions_24h ?? 0;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Referrals Admin</h1>
              <p className="text-sm text-gray-600 dark:text-gray-400">Unlocker health, backlog, and top referrers.</p>
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
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 mt-0.5" aria-hidden="true" />
                <div>
                  <p className="font-medium">Failed to load referrals metrics</p>
                  <p>{error}</p>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div
                className={`rounded-xl border px-4 py-5 shadow-sm transition ${
                  workersAlive > 0
                    ? 'border-green-200 bg-green-50 text-green-800'
                    : 'border-red-200 bg-red-50 text-red-800'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Workers Alive</p>
                    <p className="mt-2 text-3xl font-semibold">{numberFormatter.format(workersAlive)}</p>
                  </div>
                  <Server className="h-10 w-10 opacity-80" aria-hidden="true" />
                </div>
                {health?.workers?.length ? (
                  <p className="mt-3 text-xs">{health.workers.join(', ')}</p>
                ) : (
                  <p className="mt-3 text-xs">No workers responding</p>
                )}
              </div>

              <div
                className={`rounded-xl border px-4 py-5 shadow-sm transition ${
                  backlogDue > 0
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-gray-200 bg-white text-gray-800 dark:bg-gray-900/40 dark:text-gray-100'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Backlog Pending Due</p>
                    <p className="mt-2 text-3xl font-semibold">{numberFormatter.format(backlogDue)}</p>
                  </div>
                  <AlertCircle className="h-10 w-10 opacity-80" aria-hidden="true" />
                </div>
                <p className="mt-3 text-xs text-gray-700 dark:text-gray-300">
                  Rewards pending unlock with past-due unlock timestamps.
                </p>
              </div>

              <div className="rounded-xl border border-gray-200/80 dark:border-gray-700/60 bg-white/70 dark:bg-gray-900/40 px-4 py-5 shadow-sm">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Reward Totals</p>
                <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <dt className="text-gray-500 dark:text-gray-400">Pending</dt>
                    <dd className="font-semibold text-gray-900 dark:text-gray-100">{numberFormatter.format(pendingTotal)}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500 dark:text-gray-400">Unlocked</dt>
                    <dd className="font-semibold text-gray-900 dark:text-gray-100">{numberFormatter.format(unlockedTotal)}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500 dark:text-gray-400">Void</dt>
                    <dd className="font-semibold text-gray-900 dark:text-gray-100">{numberFormatter.format(voidTotal)}</dd>
                  </div>
                </dl>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-xl border border-gray-200/80 dark:border-gray-700/60 bg-white/70 dark:bg-gray-900/40 px-4 py-5 shadow-sm">
                <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">24h Signals</h2>
                <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <Users className="h-5 w-5 text-indigo-500" aria-hidden="true" />
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">Clicks</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">{numberFormatter.format(clicks24h)}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden="true" />
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">Attributions</p>
                      <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">{numberFormatter.format(attributions24h)}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200/80 dark:border-gray-700/60 bg-white/70 dark:bg-gray-900/40 px-4 py-5 shadow-sm">
                <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Status Breakdown</h2>
                <ul className="mt-4 space-y-2 text-sm">
                  {['pending', 'unlocked', 'redeemed', 'void'].map((key) => (
                    <li key={key} className="flex items-center justify-between">
                      <span className="capitalize text-gray-600 dark:text-gray-400">{key}</span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">{numberFormatter.format(counts[key] ?? 0)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="rounded-xl border border-gray-200/80 dark:border-gray-700/60 bg-white/70 dark:bg-gray-900/40 shadow-sm overflow-hidden">
              <div className="px-4 py-4 sm:px-6">
                <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">Top Referrers (20)</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-900/60">
                    <tr>
                      <th scope="col" className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">User ID</th>
                      <th scope="col" className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">Rewards</th>
                      <th scope="col" className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">Code</th>
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

            {loadingData && (
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
