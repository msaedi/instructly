'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { RefreshCw, Loader2, CheckCircle2, XCircle, Copy } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { useQueryClient } from '@tanstack/react-query';

import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

import {
  useAdminInstructorDetail,
  useBGCCounts,
  useBGCCases,
  useBGCOverride,
  useBGCDisputeOpen,
  useBGCDisputeResolve,
  type AdminInstructorDetail,
  type BGCCaseItem,
} from './hooks';

function LoadingScreen() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
    </div>
  );
}

export default function AdminBGCReviewPage() {
  const { isAdmin, isLoading: authLoading } = useAdminAuth();
  const { logout } = useAuth();
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<'review' | 'pending' | 'all'>('review');
  const [searchTerm, setSearchTerm] = useState('');
  const [onlyRecentConsent, setOnlyRecentConsent] = useState(false);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [isPreviewOpen, setPreviewOpen] = useState(false);
  const [disputeNoteDraft, setDisputeNoteDraft] = useState('');
  const previewDetail = useAdminInstructorDetail(isPreviewOpen ? previewId : null);

  const countsQuery = useBGCCounts();
  const counts = countsQuery.data ?? { review: 0, pending: 0 };
  const totalCases = counts.review + counts.pending;

  const queryTerm = searchTerm.trim();
  const { data, isLoading, isFetching } = useBGCCases(statusFilter, queryTerm, 50);

  const overrideMutation = useBGCOverride();
  const openDisputeMutation = useBGCDisputeOpen();
  const resolveDisputeMutation = useBGCDisputeResolve();

  const items = useMemo<BGCCaseItem[]>(() => data?.items ?? [], [data]);

  useEffect(() => {
    if (!isPreviewOpen) {
      setDisputeNoteDraft('');
      return;
    }
    if (previewDetail.data) {
      setDisputeNoteDraft(previewDetail.data.bgc_dispute_note ?? '');
    }
  }, [isPreviewOpen, previewDetail.data]);

  const filteredItems = useMemo<BGCCaseItem[]>(() => {
    const term = searchTerm.trim().toLowerCase();
    return items.filter((item) => {
      const matchesSearch =
        !term ||
        item.instructor_id.toLowerCase().includes(term) ||
        (item.email && item.email.toLowerCase().includes(term)) ||
        (item.name && item.name.toLowerCase().includes(term)) ||
        (item.bgc_report_id && item.bgc_report_id.toLowerCase().includes(term));
      const matchesConsent = !onlyRecentConsent || item.consent_recent;
      return matchesSearch && matchesConsent;
    });
  }, [items, onlyRecentConsent, searchTerm]);

  const statusOptions = useMemo(
    () => [
      { value: 'review' as const, label: 'Review', count: counts.review },
      { value: 'pending' as const, label: 'Pending', count: counts.pending },
      { value: 'all' as const, label: 'All', count: totalCases },
    ],
    [counts.pending, counts.review, totalCases],
  );

  const isRefreshing = isFetching && !isLoading;

  if (authLoading) {
    return <LoadingScreen />;
  }

  if (!isAdmin) {
    return null;
  }

  const handleRefresh = () => {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin', 'bgc', 'cases'], exact: false }),
      queryClient.invalidateQueries({ queryKey: ['admin', 'bgc', 'counts'], exact: false }),
    ]);
  };

  const handleOverride = async (item: BGCCaseItem, action: 'approve' | 'reject') => {
    setActiveActionId(item.instructor_id);
    try {
      await overrideMutation.mutateAsync({ id: item.instructor_id, action });
      toast.success(action === 'approve' ? 'Background check approved' : 'Background check rejected');
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to update background check status';
      toast.error(message);
    } finally {
      setActiveActionId(null);
    }
  };

  const handleCopyId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
      toast.success('Instructor ID copied to clipboard');
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to copy instructor ID';
      toast.error(message);
    }
  };

  const handleOpenDispute = async () => {
    if (!previewId) return;
    try {
      const trimmed = disputeNoteDraft.trim();
      const response = await openDisputeMutation.mutateAsync({
        id: previewId,
        note: trimmed.length > 0 ? trimmed : null,
      });
      setDisputeNoteDraft(response.dispute_note ?? '');
      toast.success('Dispute opened');
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to open dispute';
      toast.error(message);
    }
  };

  const handleResolveDispute = async () => {
    if (!previewId) return;
    try {
      const trimmed = disputeNoteDraft.trim();
      const response = await resolveDisputeMutation.mutateAsync({
        id: previewId,
        note: trimmed.length > 0 ? trimmed : null,
      });
      setDisputeNoteDraft(response.dispute_note ?? '');
      toast.success('Dispute resolved');
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to resolve dispute';
      toast.error(message);
    }
  };

  const closePreview = () => {
    setPreviewOpen(false);
    setPreviewId(null);
    setDisputeNoteDraft('');
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
                  Background Check Review Queue
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Approve or reject background checks currently awaiting admin review.
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={handleRefresh}
                disabled={isRefreshing || isLoading}
                aria-label="Refresh review queue"
              >
                {isRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => void logout()}
                className="rounded-full"
              >
                Log out
              </Button>
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
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:gap-4">
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-3">
                  <input
                    value={searchTerm}
                    onChange={(event) => setSearchTerm(event.target.value)}
                    placeholder="Search by instructor, email, or ID"
                    className="w-full md:w-72 rounded-lg border border-gray-200 bg-white/80 px-3 py-2 text-sm text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/60 dark:border-gray-700 dark:bg-gray-900/60 dark:text-gray-100"
                  />
                  <label className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                    <input
                      type="checkbox"
                      checked={onlyRecentConsent}
                      onChange={(event) => setOnlyRecentConsent(event.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    Consent in last 24h
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  {statusOptions.map((option) => (
                    <Button
                      key={option.value}
                      type="button"
                      size="sm"
                      variant={statusFilter === option.value ? 'default' : 'outline'}
                      onClick={() => setStatusFilter(option.value)}
                    >
                      {option.label}
                      <span className="ml-2 text-xs font-medium text-gray-600 dark:text-gray-300">
                        ({option.count})
                      </span>
                    </Button>
                  ))}
                </div>
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">
                {filteredItems.length} case{filteredItems.length === 1 ? '' : 's'} in view
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-gray-200/80 dark:border-gray-700/60 bg-white/70 dark:bg-gray-900/40 backdrop-blur">
              <table className="min-w-full divide-y divide-gray-200/80 dark:divide-gray-700/60 text-sm">
                <thead className="bg-gray-50/80 dark:bg-gray-800/60 text-gray-600 dark:text-gray-300">
                  <tr>
                    <th scope="col" className="px-4 py-3 text-left font-medium">Instructor</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium">Email</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium">Report</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium">Consent</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium">Updated</th>
                    <th scope="col" className="px-4 py-3 text-left font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200/60 dark:divide-gray-800/60">
                  {isLoading ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                        <div className="inline-flex items-center gap-3">
                          <Loader2 className="h-5 w-5 animate-spin" />
                          Loading background checks…
                        </div>
                      </td>
                    </tr>
                  ) : filteredItems.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                        No cases match the current filters.
                      </td>
                    </tr>
                  ) : (
                    filteredItems.map((item) => {
                      const isProcessing =
                        overrideMutation.isPending && activeActionId === item.instructor_id;
                      const updatedAt = item.updated_at || item.bgc_completed_at || item.created_at;
                      const isLive = item.is_live;
                      const statusValue = (item.bgc_status ?? '').toLowerCase();
                      const showActions = statusValue === 'review';
                      const inDispute = item.in_dispute;
                      const badgeTone = statusValue === 'review'
                        ? 'bg-amber-50 text-amber-800 border-amber-200'
                        : statusValue === 'pending'
                        ? 'bg-sky-50 text-sky-700 border-sky-200'
                        : 'bg-gray-50 text-gray-600 border-gray-200';
                      return (
                        <tr key={item.instructor_id} className="bg-white/40 dark:bg-transparent">
                          <td className="px-4 py-3">
                            <div className="flex flex-col">
                              {isLive ? (
                                <Link
                                  href={`/instructors/${item.instructor_id}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                                >
                                  {item.name}
                                </Link>
                              ) : (
                                <button
                                  type="button"
                                  className="text-left font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                                  onClick={() => {
                                    setPreviewId(item.instructor_id);
                                    setPreviewOpen(true);
                                  }}
                                  title="Profile not public until verified & live"
                                >
                                  {item.name}
                                  <span className="ml-1 text-xs text-gray-500">(preview)</span>
                                </button>
                              )}
                              <span className="text-xs text-gray-400">{item.instructor_id}</span>
                              {inDispute ? (
                                <Badge className="mt-1 w-fit border border-rose-200 bg-rose-50 text-rose-700">
                                  Dispute
                                </Badge>
                              ) : null}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{item.email || '—'}</td>
                          <td className="px-4 py-3">
                            {item.bgc_report_id ? (
                              <Link
                                href={item.checkr_report_url ?? '#'}
                                target="_blank"
                                className="text-indigo-600 hover:underline dark:text-indigo-300"
                                rel="noreferrer"
                              >
                                {item.bgc_report_id}
                              </Link>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {item.consent_recent ? (
                              <span className="inline-flex items-center gap-1 text-emerald-600 text-xs font-medium">
                                <CheckCircle2 className="h-4 w-4" /> Recent
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-gray-500 text-xs">
                                <XCircle className="h-4 w-4" /> Stale
                              </span>
                            )}
                            {item.consent_recent_at ? (
                              <div className="text-[10px] text-gray-400">
                                {formatDistanceToNow(new Date(item.consent_recent_at), { addSuffix: true })}
                              </div>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                            {updatedAt
                              ? `${formatDistanceToNow(new Date(updatedAt), { addSuffix: true })}`
                              : '—'}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className={`${badgeTone} capitalize`}>
                                {statusValue || 'unknown'}
                              </Badge>
                              {showActions ? (
                                <>
                                  <Button
                                    type="button"
                                    size="sm"
                                    onClick={() => handleOverride(item, 'approve')}
                                    disabled={isProcessing}
                                  >
                                    Approve
                                  </Button>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="destructive"
                                    onClick={() => handleOverride(item, 'reject')}
                                    disabled={isProcessing || inDispute}
                                    title={inDispute ? 'Resolve dispute before rejecting' : undefined}
                                  >
                                    Reject
                                  </Button>
                                </>
                              ) : null}
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={() => handleCopyId(item.instructor_id)}
                              >
                                <Copy className="h-4 w-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {isPreviewOpen && (
              <div className="fixed inset-0 z-40 flex items-stretch justify-end">
                <div className="absolute inset-0 bg-black/30" onClick={closePreview} />
                <div className="relative h-full w-full max-w-md bg-white dark:bg-gray-900 shadow-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6 overflow-y-auto">
                  <div className="flex items-start justify-between">
                    <div>
                      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Instructor Preview</h2>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        View instructor details before approving a non-live profile.
                      </p>
                    </div>
                    <Button type="button" variant="ghost" onClick={closePreview}>
                      Close
                    </Button>
                  </div>
                  <div className="mt-4 space-y-3 text-sm text-gray-700 dark:text-gray-200">
                    {previewDetail.isLoading ? (
                      <div className="flex items-center gap-2 text-gray-500">
                        <Loader2 className="h-4 w-4 animate-spin" /> Loading instructor…
                      </div>
                    ) : previewDetail.error ? (
                      <div className="text-red-600">Unable to load instructor information.</div>
                    ) : previewDetail.data ? (
                      <PreviewContent
                        detail={previewDetail.data}
                        disputeNote={disputeNoteDraft}
                        onDisputeNoteChange={setDisputeNoteDraft}
                        onOpenDispute={handleOpenDispute}
                        onResolveDispute={handleResolveDispute}
                        openPending={openDisputeMutation.isPending}
                        resolvePending={resolveDisputeMutation.isPending}
                      />
                    ) : (
                      <div>No instructor selected.</div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function PreviewContent({
  detail,
  disputeNote,
  onDisputeNoteChange,
  onOpenDispute,
  onResolveDispute,
  openPending,
  resolvePending,
}: {
  detail: AdminInstructorDetail;
  disputeNote: string;
  onDisputeNoteChange: (value: string) => void;
  onOpenDispute: () => void;
  onResolveDispute: () => void;
  openPending: boolean;
  resolvePending: boolean;
}) {
  const openedLabel = detail.bgc_dispute_opened_at
    ? formatDistanceToNow(new Date(detail.bgc_dispute_opened_at), { addSuffix: true })
    : null;
  const resolvedLabel = detail.bgc_dispute_resolved_at
    ? formatDistanceToNow(new Date(detail.bgc_dispute_resolved_at), { addSuffix: true })
    : null;

  return (
    <dl className="space-y-3">
      <div>
        <dt className="text-xs uppercase text-gray-400">Name</dt>
        <dd className="font-medium">{detail.name || '—'}</dd>
      </div>
      <div>
        <dt className="text-xs uppercase text-gray-400">Email</dt>
        <dd>{detail.email || '—'}</dd>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <dt className="text-xs uppercase text-gray-400">Live status</dt>
          <dd>{detail.is_live ? 'Live' : 'Not live'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-gray-400">BGC status</dt>
          <dd>{detail.bgc_status || '—'}</dd>
        </div>
      </div>
      <div>
        <dt className="text-xs uppercase text-gray-400">Consent recent at</dt>
        <dd>
          {detail.consent_recent_at
            ? formatDistanceToNow(new Date(detail.consent_recent_at), { addSuffix: true })
            : '—'}
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase text-gray-400">Checkr report</dt>
        <dd>
          {detail.bgc_report_id ? (
            <Link
              href={`https://dashboard.checkr.com/reports/${detail.bgc_report_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-indigo-600 hover:underline"
            >
              {detail.bgc_report_id}
            </Link>
          ) : (
            '—'
          )}
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase text-gray-400">Dispute status</dt>
        <dd className="flex flex-col gap-1">
          {detail.bgc_in_dispute ? (
            <Badge className="w-fit border border-rose-200 bg-rose-50 text-rose-700">In dispute</Badge>
          ) : (
            <span className="text-gray-500 dark:text-gray-400">No active dispute</span>
          )}
          {openedLabel ? (
            <span className="text-xs text-gray-500 dark:text-gray-400">Opened {openedLabel}</span>
          ) : null}
          {resolvedLabel ? (
            <span className="text-xs text-gray-500 dark:text-gray-400">Last resolved {resolvedLabel}</span>
          ) : null}
        </dd>
      </div>
      <div>
        <dt className="text-xs uppercase text-gray-400">Dispute note</dt>
        <dd>
          <textarea
            value={disputeNote}
            onChange={(event) => onDisputeNoteChange(event.target.value)}
            rows={4}
            placeholder="Document dispute context or resolution steps"
            className="mt-1 w-full rounded-lg border border-gray-200 bg-white/80 px-3 py-2 text-sm text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/60 dark:border-gray-700 dark:bg-gray-900/60 dark:text-gray-100"
          />
        </dd>
      </div>
      <div className="flex flex-wrap items-center gap-3 pt-2">
        <Button
          type="button"
          size="sm"
          onClick={onOpenDispute}
          disabled={openPending || detail.bgc_in_dispute}
        >
          {openPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Open dispute
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onResolveDispute}
          disabled={resolvePending || !detail.bgc_in_dispute}
        >
          {resolvePending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Resolve dispute
        </Button>
      </div>
    </dl>
  );
}
