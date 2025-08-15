'use client';

import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import Link from 'next/link';
import { RefreshCw, BarChart3, Table } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { AnalyticsNav } from '../AnalyticsNav';
import {
  analyticsApi,
  CandidateSummary,
  CandidateCategoryTrend,
  CandidateTopService,
} from '@/lib/analyticsApi';

export default function CandidatesAnalyticsDashboard() {
  const { isAdmin, isLoading: authLoading } = useAdminAuth();
  const { logout } = useAuth();

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<CandidateSummary | null>(null);
  const [trends, setTrends] = useState<CandidateCategoryTrend[]>([]);
  const [topServices, setTopServices] = useState<CandidateTopService[]>([]);
  const [drilldown, setDrilldown] = useState<{ serviceId: string; serviceName: string; rows: Array<{ searched_at: string; search_query: string; results_count: number | null; position: number; score: number | null; source: string | null }> } | null>(null);
  const [scoreDist, setScoreDist] = useState<{ gte_0_90: number; gte_0_80_lt_0_90: number; gte_0_70_lt_0_80: number; lt_0_70: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [s, t, ts, sd] = await Promise.all([
        analyticsApi.getCandidatesSummary(token, days),
        analyticsApi.getCandidateCategoryTrends(token, days),
        analyticsApi.getCandidateTopServices(token, days, 20),
        analyticsApi.getCandidateScoreDistribution(token, days),
      ]);
      setSummary(s);
      setTrends(t);
      setTopServices(ts);
      setScoreDist(sd);
    } catch (e: any) {
      setError(e?.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, days]);

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }
  if (!isAdmin) return null;

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
              <h1 className="text-xl font-semibold">Candidates Analytics</h1>
            </div>
            <div className="flex items-center space-x-3">
              <DaysSelector value={days} onChange={setDays} />
              <button
                onClick={refresh}
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

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Tabs */}
        <div className="mb-6">
          <AnalyticsNav />
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex items-center">
              <span className="text-red-700 dark:text-red-300">{error}</span>
            </div>
          </div>
        )}

        {/* Summary */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <SummaryCard title="Total Candidates" value={summary?.total_candidates ?? 0} />
          <SummaryCard title="Events with Candidates" value={summary?.events_with_candidates ?? 0} />
          <SummaryCard title="Avg Candidates/Event" value={summary?.avg_candidates_per_event ?? 0} />
          <SummaryCard title="Zero-Result Events w/ Candidates" value={summary?.zero_result_events_with_candidates ?? 0} />
        </div>

        {/* Trends & Score distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <CategoryTrendsChart data={trends} loading={loading} />
          <ScoreDistributionCard dist={scoreDist} loading={loading} />
        </div>

        {/* Top Services Table */}
        <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Top Services by Candidate Frequency</h3>
            <BarChart3 className="h-5 w-5 text-indigo-600" />
          </div>
          {!topServices || topServices.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400 text-center py-8">No data available</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left border-b border-gray-200 dark:border-gray-700">
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Service</th>
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Category</th>
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Candidates</th>
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Avg Score</th>
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Avg Position</th>
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Supply</th>
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Opportunity</th>
                    <th className="pb-3 pr-4 font-medium text-gray-700 dark:text-gray-300">Drill-down</th>
                  </tr>
                </thead>
                <tbody>
                  {topServices.map((item, i) => (
                    <>
                      <tr key={`row-${i}`} className="border-b border-gray-100 dark:border-gray-700">
                        <td className="py-3 pr-4 text-gray-900 dark:text-gray-100">{item.service_name}</td>
                        <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">{item.category_name}</td>
                        <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">{item.candidate_count}</td>
                        <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">{item.avg_score.toFixed(2)}</td>
                        <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">{item.avg_position.toFixed(1)}</td>
                        <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">{item.active_instructors}</td>
                        <td className="py-3 pr-4 text-gray-900 dark:text-gray-100 font-medium">{item.opportunity_score.toFixed(2)}</td>
                        <td className="py-3 pr-4">
                          <button
                            className="text-indigo-600 hover:underline"
                            onClick={async () => {
                              if (!token) return;
                              // Toggle behavior: close if already open
                              if (drilldown && drilldown.serviceId === item.service_catalog_id) {
                                setDrilldown(null);
                                return;
                              }
                              const rows = await analyticsApi.getCandidateServiceQueries(token, item.service_catalog_id, days, 50);
                              setDrilldown({ serviceId: item.service_catalog_id, serviceName: item.service_name, rows });
                            }}
                          >
                            {drilldown && drilldown.serviceId === item.service_catalog_id ? 'Hide' : 'View queries'}
                          </button>
                        </td>
                      </tr>
                      {drilldown && drilldown.serviceId === item.service_catalog_id && (
                        <tr key={`drill-${i}`} className="border-b border-gray-100 dark:border-gray-700">
                          <td colSpan={8} className="py-3 pr-4">
                            <div className="rounded-xl p-4 bg-white/60 dark:bg-gray-900/40 ring-1 ring-gray-200/70 dark:ring-gray-700/60">
                              <div className="flex items-center justify-between mb-2">
                                <h4 className="font-medium text-gray-900 dark:text-gray-100">Queries for {drilldown.serviceName}</h4>
                                <button className="text-gray-600 hover:underline" onClick={() => setDrilldown(null)}>Close</button>
                              </div>
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="text-left border-b border-gray-200 dark:border-gray-700">
                                      <th className="py-2 pr-4">When</th>
                                      <th className="py-2 pr-4">Query</th>
                                      <th className="py-2 pr-4">Results</th>
                                      <th className="py-2 pr-4">Position</th>
                                      <th className="py-2 pr-4">Score</th>
                                      <th className="py-2 pr-4">Source</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {drilldown.rows.map((r, idx) => (
                                      <tr key={idx} className="border-b border-gray-100 dark:border-gray-700">
                                        <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">{new Date(r.searched_at).toLocaleString()}</td>
                                        <td className="py-2 pr-4 text-gray-900 dark:text-gray-100">{r.search_query}</td>
                                        <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">{r.results_count ?? 0}</td>
                                        <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">{r.position}</td>
                                        <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">{r.score != null ? r.score.toFixed(2) : '-'}</td>
                                        <td className="py-2 pr-4 text-gray-600 dark:text-gray-400">{r.source || '-'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function DaysSelector({ value, onChange }: { value: number; onChange: (d: number) => void }) {
  const options = [7, 14, 30, 60, 90];
  return (
    <select
      className="h-9 rounded-full px-3 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40"
      value={value}
      onChange={(e) => onChange(parseInt(e.target.value, 10))}
    >
      {options.map((d) => (
        <option key={d} value={d}>
          Last {d} days
        </option>
      ))}
    </select>
  );
}

function SummaryCard({ title, value }: { title: string; value: number }) {
  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <div className="text-sm text-gray-600 dark:text-gray-400">{title}</div>
      <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-gray-100">{value}</div>
    </div>
  );
}

function CategoryTrendsChart({ data, loading }: { data: CandidateCategoryTrend[]; loading: boolean }) {
  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Category Trends</h3>
        <Table className="h-5 w-5 text-indigo-600" />
      </div>
      {loading ? (
        <div className="animate-pulse h-40 bg-gray-100 dark:bg-gray-800 rounded" />
      ) : !data || data.length === 0 ? (
        <p className="text-gray-500 dark:text-gray-400 text-center py-8">No data available</p>
      ) : (
        <div className="space-y-3 max-h-64 overflow-y-auto">
          {data.slice(0, 20).map((row, i) => (
            <div key={i} className="flex items-center justify-between">
              <span className="text-gray-700 dark:text-gray-300">{row.date} · {row.category}</span>
              <span className="text-gray-900 dark:text-gray-100 font-medium">{row.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScoreDistributionCard({
  dist,
  loading,
}: {
  dist: { gte_0_90: number; gte_0_80_lt_0_90: number; gte_0_70_lt_0_80: number; lt_0_70: number } | null;
  loading: boolean;
}) {
  const items = useMemo(
    () => [
      { label: '≥ 0.90', value: dist?.gte_0_90 ?? 0 },
      { label: '0.80–0.89', value: dist?.gte_0_80_lt_0_90 ?? 0 },
      { label: '0.70–0.79', value: dist?.gte_0_70_lt_0_80 ?? 0 },
      { label: '< 0.70', value: dist?.lt_0_70 ?? 0 },
    ],
    [dist]
  );

  return (
    <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Score Distribution</h3>
      </div>
      {loading ? (
        <div className="animate-pulse h-40 bg-gray-100 dark:bg-gray-800 rounded" />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {items.map((it) => (
            <div key={it.label} className="rounded-xl p-4 bg-white/60 dark:bg-gray-900/40 ring-1 ring-gray-200/70 dark:ring-gray-700/60">
              <div className="text-sm text-gray-600 dark:text-gray-400">{it.label}</div>
              <div className="mt-2 text-xl font-semibold text-gray-900 dark:text-gray-100">{it.value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
