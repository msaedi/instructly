// frontend/app/(admin)/admin/badges/pending/page.tsx
'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, ShieldCheck, ShieldOff } from 'lucide-react';
import { toast } from 'sonner';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { badgesApi } from '@/services/api/badges';
import type { AdminAward } from '@/types/badges';
import { queryKeys } from '@/lib/react-query/queryClient';
import { cn } from '@/lib/utils';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

type StatusFilter = 'pending' | 'confirmed' | 'revoked';

const STATUS_FILTERS = {
  PENDING: 'pending',
  CONFIRMED: 'confirmed',
  REVOKED: 'revoked',
} as const;

const DEFAULT_LIMIT = 50;

const statusColors: Record<StatusFilter, string> = {
  pending: 'text-amber-600 bg-amber-100',
  confirmed: 'text-green-700 bg-green-100',
  revoked: 'text-gray-600 bg-gray-200',
};

export default function AdminPendingBadgesPage() {
  const { isAdmin, isLoading } = useAdminAuth();
  const { logout } = useAuth();
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>(STATUS_FILTERS.PENDING);
  const [beforeFilter, setBeforeFilter] = useState('');
  const [offset, setOffset] = useState(0);

  const params = useMemo(() => {
    const query: Record<string, unknown> = {
      status: statusFilter,
      limit: DEFAULT_LIMIT,
      offset,
    };
    if (beforeFilter) {
      const parsed = new Date(beforeFilter);
      if (!Number.isNaN(parsed.getTime())) {
        query['before'] = parsed.toISOString();
      }
    }
    return query;
  }, [statusFilter, beforeFilter, offset]);

  const {
    data,
    isFetching,
    isLoading: isQueryLoading,
    isError,
    error,
  } = useQuery({
    queryKey: queryKeys.badges.admin(params),
    queryFn: () => badgesApi.listPendingAwards(params),
    placeholderData: (previous) => previous,
  });

  const [actioningId, setActioningId] = useState<string | null>(null);

  const confirmMutation = useMutation({
    mutationFn: badgesApi.confirmAward,
    onMutate: (awardId: string) => {
      setActioningId(awardId);
    },
    onSuccess: (updated) => {
      updateAwardInCache(updated);
      toast.success(`${updated.badge.name} confirmed`);
    },
    onError: (mutationError: Error) => {
      toast.error(mutationError.message || 'Unable to confirm award');
    },
    onSettled: () => {
      setActioningId(null);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: badgesApi.revokeAward,
    onMutate: (awardId: string) => {
      setActioningId(awardId);
    },
    onSuccess: (updated) => {
      updateAwardInCache(updated);
      toast.success(`${updated.badge.name} revoked`);
    },
    onError: (mutationError: Error) => {
      toast.error(mutationError.message || 'Unable to revoke award');
    },
    onSettled: () => {
      setActioningId(null);
    },
  });

  function updateAwardInCache(updated: AdminAward) {
    queryClient.setQueryData(queryKeys.badges.admin(params), (current: typeof data) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item) => (item.award_id === updated.award_id ? updated : item)),
      };
    });
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const isEmpty = !isQueryLoading && items.length === 0;
  const canPrev = offset > 0;
  const canNext =
    typeof data?.next_offset === 'number'
      ? data.next_offset > offset
      : offset + DEFAULT_LIMIT < total;

  const handleStatusChange = (value: StatusFilter) => {
    setStatusFilter(value);
    setOffset(0);
  };

  const handleBeforeChange: React.ChangeEventHandler<HTMLInputElement> = (event) => {
    setBeforeFilter(event.target.value);
    setOffset(0);
  };

  const handleNext = () => {
    if (typeof data?.next_offset === 'number') {
      setOffset(data.next_offset);
    } else {
      setOffset((prev) => prev + DEFAULT_LIMIT);
    }
  };

  const handlePrev = () => {
    setOffset((prev) => Math.max(0, prev - DEFAULT_LIMIT));
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Loader2 className="h-8 w-8 animate-spin text-purple-600" aria-label="Loading admin view" />
      </div>
    );
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link
                href="/"
                className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8"
              >
                iNSTAiNSTRU
              </Link>
              <div>
                <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Badge Reviews</h1>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Review badges before they are confirmed for students.
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              {isFetching && (
                <Loader2 className="h-4 w-4 animate-spin text-purple-600" aria-label="Refreshing badge data" />
              )}
              <button
                type="button"
                onClick={() => logout()}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3">
            <AdminSidebar />
          </aside>

          <section className="col-span-12 md:col-span-9">
            <div className="rounded-2xl bg-white/60 dark:bg-gray-900/40 backdrop-blur p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60">
              <div className="flex flex-wrap items-center gap-4 mb-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Pending Awards</h2>
                  <p className="text-sm text-gray-600">
                    Review badges before they are confirmed for students.
                  </p>
                </div>

                <div className="ml-auto flex flex-wrap gap-3 items-center">
                  <div className="flex flex-col">
                    <label htmlFor="status-filter" className="text-xs font-medium text-gray-500">
                      Status
                    </label>
                    <Select value={statusFilter} onValueChange={(value: StatusFilter) => handleStatusChange(value)}>
                      <SelectTrigger
                        id="status-filter"
                        className="inline-flex items-center justify-between w-40 rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800"
                      >
                        <SelectValue placeholder="Status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={STATUS_FILTERS.PENDING}>Pending</SelectItem>
                        <SelectItem value={STATUS_FILTERS.CONFIRMED}>Confirmed</SelectItem>
                        <SelectItem value={STATUS_FILTERS.REVOKED}>Revoked</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col">
                    <label htmlFor="before-date" className="text-xs font-medium text-gray-500">
                      Awarded before
                    </label>
                    <input
                      id="before-date"
                      type="date"
                      value={beforeFilter}
                      onChange={handleBeforeChange}
                      className="rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-purple-200"
                    />
                  </div>
                </div>
              </div>

              {isError && (
                <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error instanceof Error ? error.message : 'Unable to load badge data.'}
                </div>
              )}

              {isEmpty && (
                <div className="rounded-xl border border-dashed border-purple-200 bg-purple-50 p-6 text-sm text-purple-800">
                  No badge awards match this filter.
                </div>
              )}

              {!isEmpty && (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th scope="col" className="px-4 py-3 text-left font-semibold text-gray-700">
                          Student
                        </th>
                        <th scope="col" className="px-4 py-3 text-left font-semibold text-gray-700">
                          Badge
                        </th>
                        <th scope="col" className="px-4 py-3 text-left font-semibold text-gray-700">
                          Status
                        </th>
                        <th scope="col" className="px-4 py-3 text-left font-semibold text-gray-700">
                          Awarded
                        </th>
                        <th scope="col" className="px-4 py-3 text-left font-semibold text-gray-700">
                          Hold Until
                        </th>
                        <th scope="col" className="px-4 py-3 text-right font-semibold text-gray-700">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {items.map((award) => (
                        <tr key={award.award_id} className="bg-white">
                          <td className="px-4 py-3">
                            <div className="font-medium text-gray-900">
                              {award.student.display_name || award.student.email || award.student.id}
                            </div>
                            <div className="text-xs text-gray-500">{award.student.email}</div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-semibold text-gray-900">{award.badge.name}</div>
                            <div className="text-xs text-gray-500">{award.badge.slug}</div>
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={cn(
                                'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold',
                                statusColors[award.status as StatusFilter] || 'bg-gray-100 text-gray-600'
                              )}
                            >
                              {award.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700">
                            {new Date(award.awarded_at).toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700">
                            {award.hold_until ? new Date(award.hold_until).toLocaleString() : '—'}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-3 py-1 text-xs font-semibold text-green-700 hover:bg-green-100 disabled:opacity-50"
                                onClick={() => confirmMutation.mutate(award.award_id)}
                                disabled={award.status !== 'pending' || actioningId === award.award_id}
                              >
                                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                                Confirm
                              </button>
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
                                onClick={() => revokeMutation.mutate(award.award_id)}
                                disabled={award.status === 'revoked' || actioningId === award.award_id}
                              >
                                <ShieldOff className="h-3.5 w-3.5" aria-hidden="true" />
                                Revoke
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="mt-4 flex items-center justify-between">
                <p className="text-xs text-gray-500">
                  Showing {items.length} of {total} awards
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="rounded-md border border-gray-200 px-3 py-1 text-sm text-gray-700 disabled:opacity-50"
                    onClick={handlePrev}
                    disabled={!canPrev}
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-gray-200 px-3 py-1 text-sm text-gray-700 disabled:opacity-50"
                    onClick={handleNext}
                    disabled={!canNext}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
