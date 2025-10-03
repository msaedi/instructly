'use client';

import { useMemo, useState } from 'react';
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

import { useBGCOverride, useBGCReviewList, type BGCReviewItem } from './hooks';

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

  const {
    data,
    isLoading,
    isFetching,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useBGCReviewList(50);

  const overrideMutation = useBGCOverride();

  const [searchTerm, setSearchTerm] = useState('');
  const [onlyRecentConsent, setOnlyRecentConsent] = useState(false);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);

  const items = useMemo<BGCReviewItem[]>(() => {
    const pages = data?.pages ?? [];
    return pages.flatMap<BGCReviewItem>((page) => page.items ?? []);
  }, [data?.pages]);

  const filteredItems = useMemo<BGCReviewItem[]>(() => {
    const term = searchTerm.trim().toLowerCase();
    return items.filter((item) => {
      const matchesSearch =
        !term ||
        item.instructor_id.toLowerCase().includes(term) ||
        (item.email && item.email.toLowerCase().includes(term)) ||
        (item.name && item.name.toLowerCase().includes(term));
      const matchesConsent = !onlyRecentConsent || item.consented_at_recent;
      return matchesSearch && matchesConsent;
    });
  }, [items, onlyRecentConsent, searchTerm]);

  const isRefreshing = isFetching && !isFetchingNextPage && !isLoading;

  if (authLoading) {
    return <LoadingScreen />;
  }

  if (!isAdmin) {
    return null;
  }

  const handleRefresh = () => {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin', 'bgc', 'review', 'list'], exact: false }),
      queryClient.invalidateQueries({ queryKey: ['admin', 'bgc', 'review', 'count'], exact: false }),
    ]);
  };

  const handleOverride = async (item: BGCReviewItem, action: 'approve' | 'reject') => {
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
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
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
                        Nothing in review right now.
                      </td>
                    </tr>
                  ) : (
                    filteredItems.map((item) => {
                      const isProcessing = overrideMutation.isPending && activeActionId === item.instructor_id;
                      const updatedAt = item.bgc_completed_at || item.created_at;
                      return (
                        <tr key={item.instructor_id} className="bg-white/40 dark:bg-transparent">
                          <td className="px-4 py-3">
                            <div className="flex flex-col">
                              <Link
                                href={`/instructors/${item.instructor_id}`}
                                target="_blank"
                                className="font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                              >
                                {item.name}
                              </Link>
                              <span className="text-xs text-gray-400">{item.instructor_id}</span>
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
                            {item.consented_at_recent ? (
                              <span className="inline-flex items-center gap-1 text-emerald-600 text-xs font-medium">
                                <CheckCircle2 className="h-4 w-4" /> Recent
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-gray-500 text-xs">
                                <XCircle className="h-4 w-4" /> Stale
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                            {updatedAt
                              ? `${formatDistanceToNow(new Date(updatedAt), { addSuffix: true })}`
                              : '—'}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className="bg-amber-50 text-amber-800 border-amber-200">
                                review
                              </Badge>
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
                                disabled={isProcessing}
                              >
                                Reject
                              </Button>
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

            {hasNextPage && (
              <div className="flex justify-center">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                  className="min-w-[140px]"
                >
                  {isFetchingNextPage ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Load more'}
                </Button>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
