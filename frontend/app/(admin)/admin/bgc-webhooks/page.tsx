'use client';

import Link from 'next/link';
import { Dispatch, SetStateAction, useEffect, useMemo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { Copy, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { useBGCWebhookLogs, type WebhookLogItem } from './hooks';

const EVENT_FILTERS = [
  { label: 'Invitations', value: 'invitation.' },
  { label: 'Reports', value: 'report.' },
  { label: 'Completed', value: 'completed' },
  { label: 'Deferred', value: 'deferred' },
  { label: 'Canceled', value: 'canceled' },
  { label: 'Errors', value: 'error' },
] as const;

const STATUS_FILTERS = [
  { label: '2xx', value: '2xx' },
  { label: '4xx', value: '4xx' },
  { label: '5xx', value: '5xx' },
] as const;

const MAX_LOG_LIMIT = 50;

function LoadingScreen() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600" />
    </div>
  );
}

export default function BGCWebhookLogPage() {
  const { isAdmin, isLoading: authLoading } = useAdminAuth();
  const { logout } = useAuth();

  const [eventFilters, setEventFilters] = useState<string[]>(['report.']);
  const [statusFilters, setStatusFilters] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [selectedLog, setSelectedLog] = useState<WebhookLogItem | null>(null);

  const filters = useMemo(
    () => ({
      events: eventFilters,
      statuses: statusFilters,
      search: searchTerm,
      limit: MAX_LOG_LIMIT,
      autoRefresh,
    }),
    [eventFilters, statusFilters, searchTerm, autoRefresh],
  );

  const {
    logs,
    errorCount24h,
    fetchNextPage,
    hasNextPage,
    isPending,
    isFetching,
    isFetchingNextPage,
    refetch,
  } = useBGCWebhookLogs(filters);

  useEffect(() => {
    window.dispatchEvent(new Event('bgc-webhooks-refresh'));
  }, [errorCount24h]);

  const errorDisplay = typeof errorCount24h === 'number' ? errorCount24h : 0;

  if (authLoading) return <LoadingScreen />;
  if (!isAdmin) {
    void logout();
    return null;
  }

  const isRefreshing = isFetching && !isPending;

  const toggleFilter = (value: string, setState: Dispatch<SetStateAction<string[]>>) => {
    setState((prev) => (prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]));
  };

  const handleCopy = async (label: string, value: string | null | undefined) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copied`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to copy value';
      toast.error(message);
    }
  };

  const openJsonViewer = (log: WebhookLogItem) => {
    setSelectedLog(log);
  };

  const closeJsonViewer = () => {
    setSelectedLog(null);
  };

  const statusBadgeTone = (statusCode?: number | null) => {
    if (!statusCode) return 'bg-gray-100 text-gray-700 border-gray-200';
    if (statusCode >= 500) return 'bg-rose-100 text-rose-700 border-rose-200';
    if (statusCode >= 400) return 'bg-amber-100 text-amber-800 border-amber-200';
    return 'bg-emerald-100 text-emerald-700 border-emerald-200';
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-6">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400">
                iNSTAiNSTRU
              </Link>
              <div>
                <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Background Check Webhook Log
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Last 200 deliveries · {errorDisplay} error{errorDisplay === 1 ? '' : 's'} in the past 24h
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3">
              <label className="flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(event) => setAutoRefresh(event.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  aria-label="Toggle auto refresh"
                />
                Auto-refresh every 15s
              </label>
              <button
                type="button"
                onClick={() => refetch()}
                disabled={isRefreshing || isPending}
                aria-label="Refresh webhook log"
                className="inline-flex h-9 w-9 items-center justify-center rounded-full text-indigo-600 hover:text-white hover:bg-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/70 disabled:opacity-50"
              >
                {isRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => void logout()}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60"
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
            <Card className="rounded-2xl border border-gray-200/80 bg-white/80 shadow-sm dark:border-gray-800/60 dark:bg-gray-900/40 backdrop-blur">
              <CardHeader className="pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  {EVENT_FILTERS.map((filter) => {
                    const active = eventFilters.includes(filter.value);
                    return (
                      <button
                        key={filter.value}
                        type="button"
                        onClick={() => toggleFilter(filter.value, setEventFilters)}
                        className={`inline-flex items-center rounded-full px-4 py-1.5 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-indigo-500/60 ${
                          active
                            ? 'bg-indigo-600 text-white shadow'
                            : 'text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/70 dark:bg-gray-900/40'
                        }`}
                        aria-pressed={active}
                      >
                        {filter.label}
                      </button>
                    );
                  })}
                </div>
              </CardHeader>
              <CardContent className="space-y-4 pt-4">
                <div className="flex flex-wrap items-center gap-3">
                  {STATUS_FILTERS.map((filter) => {
                    const active = statusFilters.includes(filter.value);
                    return (
                      <button
                        key={filter.value}
                        type="button"
                        onClick={() => toggleFilter(filter.value, setStatusFilters)}
                        className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                          active
                            ? 'bg-purple-600 text-white shadow-sm'
                            : 'text-gray-600 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/70 dark:bg-gray-900/40'
                        }`}
                        aria-pressed={active}
                      >
                        {filter.label}
                      </button>
                    );
                  })}
                  <input
                    value={searchTerm}
                    onChange={(event) => setSearchTerm(event.target.value)}
                    placeholder="Search delivery or signature"
                    className="flex-1 min-w-[240px] rounded-lg border border-gray-200 bg-white/80 px-3 py-2 text-sm text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/60 dark:border-gray-700 dark:bg-gray-900/60 dark:text-gray-100"
                  />
                </div>
                <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
                  <span>
                    Showing {logs.length} entr{logs.length === 1 ? 'y' : 'ies'}
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card className="overflow-hidden rounded-2xl border border-gray-200/80 bg-white/80 shadow-sm dark:border-gray-800/60 dark:bg-gray-900/40 backdrop-blur">
              <CardContent className="p-0">
                <table className="min-w-full divide-y divide-gray-200/70 text-sm dark:divide-gray-800/60">
                  <thead className="bg-gray-50/90 text-gray-600 dark:bg-gray-900/60 dark:text-gray-300">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold">Time</th>
                      <th className="px-4 py-3 text-left font-semibold">Event</th>
                      <th className="px-4 py-3 text-left font-semibold">HTTP</th>
                      <th className="px-4 py-3 text-left font-semibold">Identifiers</th>
                      <th className="px-4 py-3 text-left font-semibold">Instructor</th>
                      <th className="px-4 py-3 text-left font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-800/50">
                    {logs.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                          {isPending ? 'Loading events…' : 'No webhook deliveries yet.'}
                        </td>
                      </tr>
                    )}
                    {logs.map((log) => (
                      <tr key={log.id} className="bg-white/70 dark:bg-gray-900/40">
                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                          <div className="font-medium text-gray-900 dark:text-gray-100">
                            {formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}
                          </div>
                          <div className="text-xs text-gray-400">
                            {new Date(log.created_at).toLocaleString()}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200">
                          <Badge variant="outline" className="font-mono uppercase tracking-wide">
                            {log.event_type}
                          </Badge>
                          {log.result ? (
                            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">result: {log.result}</div>
                          ) : null}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline" className={statusBadgeTone(log.http_status)}>
                            {log.http_status ?? '—'}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            {renderIdentifier('Delivery', log.delivery_id, () => handleCopy('Delivery ID', log.delivery_id))}
                            {renderIdentifier('Report', log.report_id, () => handleCopy('Report ID', log.report_id))}
                            {renderIdentifier('Invitation', log.invitation_id, () => handleCopy('Invitation ID', log.invitation_id))}
                            {renderIdentifier('Candidate', log.candidate_id, () => handleCopy('Candidate ID', log.candidate_id))}
                          </div>
                          {log.signature ? (
                            <button
                              type="button"
                              onClick={() => handleCopy('Signature', log.signature)}
                              className="mt-2 inline-flex items-center gap-2 text-xs text-indigo-600 hover:underline dark:text-indigo-300"
                            >
                              <Copy className="h-3 w-3" />
                              Signature
                            </button>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          {log.instructor_id ? (
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs text-gray-700 dark:text-gray-100">
                                {log.instructor_id}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleCopy('Instructor ID', log.instructor_id)}
                                className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
                              >
                                <Copy className="h-3 w-3" /> Copy
                              </button>
                            </div>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => handleCopy('Delivery ID', log.delivery_id)}
                              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:border-gray-400 dark:border-gray-700 dark:text-gray-200"
                              disabled={!log.delivery_id}
                            >
                              <Copy className="h-3 w-3" />
                              Copy delivery
                            </button>
                            <Button type="button" size="sm" variant="secondary" onClick={() => openJsonViewer(log)}>
                              View JSON
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
              {hasNextPage ? (
                <CardFooter className="border-t border-gray-200/70 bg-gray-50/70 px-4 py-4 text-center dark:border-gray-800/60 dark:bg-gray-900/40">
                  <Button type="button" variant="outline" onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
                    {isFetchingNextPage ? 'Loading…' : 'Load more'}
                  </Button>
                </CardFooter>
              ) : null}
            </Card>
          </section>
        </div>
      </main>

      {selectedLog ? (
        <div className="fixed inset-0 z-40 flex items-stretch justify-end">
          <div className="absolute inset-0 bg-black/40" onClick={closeJsonViewer} />
          <div className="relative h-full w-full max-w-2xl bg-white shadow-2xl ring-1 ring-gray-200 dark:bg-gray-900">
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-800">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide">Payload</p>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{selectedLog.event_type}</h2>
              </div>
              <Button type="button" variant="ghost" onClick={closeJsonViewer}>
                Close
              </Button>
            </div>
            <div className="h-full overflow-y-auto bg-gray-950 text-green-100">
              <pre className="whitespace-pre-wrap px-6 py-4 text-xs leading-relaxed">
                {JSON.stringify(selectedLog.payload, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function renderIdentifier(label: string, value: string | null | undefined, onCopy: () => void) {
  if (!value) return null;
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-gray-300 bg-white/70 px-2 py-1 text-xs font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-100">
      <span className="text-gray-500">{label}:</span>
      <span className="font-mono">{value}</span>
      <button type="button" className="text-indigo-600 hover:underline dark:text-indigo-300" onClick={onCopy}>
        Copy
      </button>
    </div>
  );
}
