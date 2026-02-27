// frontend/app/(admin)/admin/location-learning/page.tsx
'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, RefreshCw, Trash2 } from 'lucide-react';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';
import { CreateAliasModal } from './CreateAliasModal';
import type {
  ApiErrorResponse,
  LocationLearningPendingAliasesResponse,
  LocationLearningUnresolvedQueriesResponse,
} from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

type UnresolvedQueriesResponse = LocationLearningUnresolvedQueriesResponse;
type PendingAliasesResponse = LocationLearningPendingAliasesResponse;

async function fetchUnresolved(limit = 50): Promise<UnresolvedQueriesResponse> {
  const res = await fetchWithAuth(`/api/v1/admin/location-learning/unresolved?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch unresolved queries');
  return res.json() as Promise<UnresolvedQueriesResponse>;
}

async function fetchPendingAliases(): Promise<PendingAliasesResponse> {
  const res = await fetchWithAuth('/api/v1/admin/location-learning/pending-aliases');
  if (!res.ok) throw new Error('Failed to fetch pending aliases');
  return res.json() as Promise<PendingAliasesResponse>;
}

async function approveAlias(aliasId: string): Promise<void> {
  const res = await fetchWithAuth(`/api/v1/admin/location-learning/aliases/${aliasId}/approve`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to approve alias');
}

async function rejectAlias(aliasId: string): Promise<void> {
  const res = await fetchWithAuth(`/api/v1/admin/location-learning/aliases/${aliasId}/reject`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to reject alias');
}

async function dismissUnresolved(queryNormalized: string): Promise<void> {
  const res = await fetchWithAuth(
    `/api/v1/admin/location-learning/unresolved/${encodeURIComponent(queryNormalized)}/dismiss`,
    { method: 'POST' },
  );
  if (!res.ok) throw new Error('Failed to dismiss query');
}

async function createManualAlias(payload: {
  alias: string;
  region_boundary_id?: string;
  candidate_region_ids?: string[];
}): Promise<void> {
  const res = await fetchWithAuth('/api/v1/admin/location-learning/aliases', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as ApiErrorResponse;
    throw new Error(extractApiErrorMessage(body, 'Failed to create alias'));
  }
}

function formatConfidence(confidence: number): string {
  if (!Number.isFinite(confidence)) return '-';
  return `${Math.round(confidence * 100)}%`;
}

export default function LocationLearningPage() {
  const { isAdmin, isLoading: authLoading } = useAdminAuth();
  const { logout } = useAuth();
  const queryClient = useQueryClient();

  const [selectedQuery, setSelectedQuery] = useState<string | null>(null);

  const unresolvedQuery = useQuery({
    queryKey: ['admin', 'location-learning', 'unresolved'],
    queryFn: () => fetchUnresolved(200),
  });

  const pendingQuery = useQuery({
    queryKey: ['admin', 'location-learning', 'pending-aliases'],
    queryFn: fetchPendingAliases,
  });

  const approveMutation = useMutation({
    mutationFn: approveAlias,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['admin', 'location-learning', 'pending-aliases'] }),
    onError: (err) => logger.error('Approve alias failed', err),
  });

  const rejectMutation = useMutation({
    mutationFn: rejectAlias,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['admin', 'location-learning', 'pending-aliases'] }),
    onError: (err) => logger.error('Reject alias failed', err),
  });

  const dismissMutation = useMutation({
    mutationFn: dismissUnresolved,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['admin', 'location-learning', 'unresolved'] }),
    onError: (err) => logger.error('Dismiss unresolved failed', err),
  });

  const createAliasMutation = useMutation({
    mutationFn: createManualAlias,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin', 'location-learning', 'unresolved'] });
      setSelectedQuery(null);
    },
    onError: (err) => logger.error('Create alias failed', err),
  });

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAdmin) return null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">
                iNSTAiNSTRU
              </Link>
              <h1 className="text-xl font-semibold">Location Learning</h1>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  void unresolvedQuery.refetch();
                  void pendingQuery.refetch();
                }}
                className="inline-flex items-center justify-center h-9 w-9 rounded-full text-indigo-600 hover:text-white hover:bg-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                title="Refresh"
              >
                <RefreshCw className="h-5 w-5" />
              </button>
              <button
                onClick={() => void logout()}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>

          <section className="col-span-12 md:col-span-9 lg:col-span-9 space-y-8">
            {/* Pending learned aliases */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">
                  Pending Learned Aliases
                  {pendingQuery.data?.aliases?.length ? (
                    <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-sm text-amber-800">
                      {pendingQuery.data.aliases.length}
                    </span>
                  ) : null}
                </h2>
              </div>

              {pendingQuery.isLoading ? (
                <div className="text-sm text-gray-500">Loading…</div>
              ) : pendingQuery.isError ? (
                <div className="flex items-center gap-2 text-sm text-red-600">
                  <AlertCircle className="h-4 w-4" />
                  Failed to load pending aliases
                </div>
              ) : pendingQuery.data?.aliases?.length ? (
                <div className="overflow-hidden rounded-lg bg-white shadow ring-1 ring-gray-200/70">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Alias</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">→ Region</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Confidence</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Clicks</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {pendingQuery.data.aliases.map((alias) => (
                        <tr key={alias.id}>
                          <td className="px-6 py-4 whitespace-nowrap font-mono text-sm">
                            &quot;{alias.alias_normalized}&quot;
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            {alias.region_name ?? alias.region_boundary_id ?? '-'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            <span className="rounded bg-gray-100 px-2 py-1 text-gray-700">
                              {formatConfidence(alias.confidence)}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">{alias.user_count}</td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                            <button
                              onClick={() => approveMutation.mutate(alias.id)}
                              disabled={approveMutation.isPending}
                              className="inline-flex items-center gap-1 rounded bg-green-600 px-3 py-1 text-white hover:bg-green-700 disabled:opacity-50"
                            >
                              <CheckCircle2 className="h-4 w-4" />
                              Approve
                            </button>
                            <button
                              onClick={() => rejectMutation.mutate(alias.id)}
                              disabled={rejectMutation.isPending}
                              className="inline-flex items-center gap-1 rounded bg-red-600 px-3 py-1 text-white hover:bg-red-700 disabled:opacity-50"
                            >
                              <Trash2 className="h-4 w-4" />
                              Reject
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-sm text-gray-500">No pending aliases to review</div>
              )}
            </div>

            {/* Unresolved queries */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">
                  Unresolved Queries
                  {unresolvedQuery.data?.queries?.length ? (
                    <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-sm text-gray-800">
                      {unresolvedQuery.data.queries.length}
                    </span>
                  ) : null}
                </h2>
              </div>

              {unresolvedQuery.isLoading ? (
                <div className="text-sm text-gray-500">Loading…</div>
              ) : unresolvedQuery.isError ? (
                <div className="flex items-center gap-2 text-sm text-red-600">
                  <AlertCircle className="h-4 w-4" />
                  Failed to load unresolved queries
                </div>
              ) : unresolvedQuery.data?.queries?.length ? (
                <div className="overflow-hidden rounded-lg bg-white shadow ring-1 ring-gray-200/70">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Query</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Searches</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Clicks</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Top Region</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {unresolvedQuery.data.queries.map((q) => {
                        const top = q.clicks?.[0];
                        const topLabel = top?.region_name
                          ? `${top.region_name} (${top.count})`
                          : top?.region_boundary_id
                          ? `${top.region_boundary_id} (${top.count})`
                          : '-';
                        return (
                          <tr key={q.id}>
                            <td className="px-6 py-4 whitespace-nowrap font-mono text-sm">
                              &quot;{q.query_normalized}&quot;
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm">{q.search_count}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm">{q.click_count ?? 0}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">{topLabel}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                              <button
                                onClick={() => setSelectedQuery(q.query_normalized)}
                                className="rounded bg-purple-600 px-3 py-1 text-white hover:bg-purple-700"
                              >
                                Create Alias
                              </button>
                              <button
                                onClick={() => dismissMutation.mutate(q.query_normalized)}
                                disabled={dismissMutation.isPending}
                                className="rounded bg-gray-200 px-3 py-1 text-gray-800 hover:bg-gray-300 disabled:opacity-50"
                              >
                                Dismiss
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-sm text-gray-500">No unresolved queries</div>
              )}
            </div>
          </section>
        </div>
      </div>

      {selectedQuery ? (
        <CreateAliasModal
          alias={selectedQuery}
          onClose={() => setSelectedQuery(null)}
          isSubmitting={createAliasMutation.isPending}
          onSubmit={(payload) => {
            createAliasMutation.mutate({
              alias: selectedQuery,
              ...(payload.regionBoundaryId ? { region_boundary_id: payload.regionBoundaryId } : {}),
              ...(payload.candidateRegionIds ? { candidate_region_ids: payload.candidateRegionIds } : {}),
            });
          }}
        />
      ) : null}
    </div>
  );
}
