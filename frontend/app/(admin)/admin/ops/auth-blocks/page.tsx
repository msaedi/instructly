'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  AlertTriangle,
  Lock,
  Zap,
  Bot,
  XCircle,
  Mail,
  CheckCircle,
  Search,
} from 'lucide-react';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { fetchWithAuth } from '@/lib/api';

// Types
interface LockoutState {
  active: boolean;
  ttl_seconds: number;
  level: string;
}

interface RateLimitState {
  active: boolean;
  count: number;
  limit: number;
  ttl_seconds: number;
}

interface CaptchaState {
  active: boolean;
}

interface BlocksState {
  lockout: LockoutState | null;
  rate_limit_minute: RateLimitState | null;
  rate_limit_hour: RateLimitState | null;
  captcha_required: CaptchaState | null;
}

interface BlockedAccount {
  email: string;
  blocks: BlocksState;
  failure_count: number;
}

interface SummaryStats {
  total_blocked: number;
  locked_out: number;
  rate_limited: number;
  captcha_required: number;
}

interface ListAuthIssuesResponse {
  accounts: BlockedAccount[];
  total: number;
  scanned_at: string;
}

interface ClearBlocksResponse {
  email: string;
  cleared: string[];
  cleared_by: string;
  cleared_at: string;
  reason: string | null;
}

// API functions
async function fetchAuthIssues(
  email?: string,
  type?: string,
): Promise<ListAuthIssuesResponse> {
  const params = new URLSearchParams();
  if (email) params.set('email', email);
  if (type && type !== 'all') params.set('type', type);

  const url = `/api/v1/admin/auth-blocks${params.toString() ? `?${params.toString()}` : ''}`;
  const response = await fetchWithAuth(url);
  if (!response.ok) {
    throw new Error('Failed to fetch auth issues');
  }
  return response.json() as Promise<ListAuthIssuesResponse>;
}

async function fetchSummaryStats(): Promise<SummaryStats> {
  const response = await fetchWithAuth('/api/v1/admin/auth-blocks/summary');
  if (!response.ok) {
    throw new Error('Failed to fetch summary stats');
  }
  return response.json() as Promise<SummaryStats>;
}

async function clearBlocks(
  email: string,
  types?: string[],
  reason?: string,
): Promise<ClearBlocksResponse> {
  const response = await fetchWithAuth(`/api/v1/admin/auth-blocks/${encodeURIComponent(email)}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ types, reason }),
  });
  if (!response.ok) {
    throw new Error('Failed to clear blocks');
  }
  return response.json() as Promise<ClearBlocksResponse>;
}

// Helper to format time
function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

// Status Card component
function StatusCard({
  label,
  value,
  icon: Icon,
  iconColor,
  warning = false,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  iconColor: string;
  warning?: boolean;
}) {
  return (
    <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">{label}</p>
          <p
            className={`text-2xl font-bold ${warning && value > 0 ? 'text-orange-600' : 'text-gray-900 dark:text-gray-100'}`}
          >
            {value}
          </p>
        </div>
        <Icon className={`h-8 w-8 ${iconColor}`} />
      </div>
    </div>
  );
}

// Blocked Account Card component
function BlockedAccountCard({
  account,
  onClear,
  isClearing,
}: {
  account: BlockedAccount;
  onClear: (email: string, types?: string[]) => void;
  isClearing: boolean;
}) {
  const [ttls, setTtls] = useState({
    lockout: account.blocks.lockout?.ttl_seconds ?? 0,
    minute: account.blocks.rate_limit_minute?.ttl_seconds ?? 0,
    hour: account.blocks.rate_limit_hour?.ttl_seconds ?? 0,
  });

  // Count down TTLs every second
  useEffect(() => {
    const interval = setInterval(() => {
      setTtls((prev) => ({
        lockout: Math.max(0, prev.lockout - 1),
        minute: Math.max(0, prev.minute - 1),
        hour: Math.max(0, prev.hour - 1),
      }));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Reset TTLs when account changes
  const hasLockout = account.blocks.lockout?.active && ttls.lockout > 0;
  const hasRateLimit =
    (account.blocks.rate_limit_minute?.active && ttls.minute > 0) ||
    (account.blocks.rate_limit_hour?.active && ttls.hour > 0);
  const hasCaptcha = account.blocks.captcha_required?.active;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4 text-gray-500" />
          <span className="font-medium text-gray-900 dark:text-gray-100">{account.email}</span>
        </div>
        <button
          onClick={() => onClear(account.email)}
          disabled={isClearing}
          className="px-3 py-1 text-sm font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300 border border-indigo-200 dark:border-indigo-700 rounded-lg hover:bg-indigo-50 dark:hover:bg-indigo-900/20 disabled:opacity-50"
        >
          {isClearing ? 'Clearing...' : 'Clear All'}
        </button>
      </div>

      <div className="space-y-2">
        {hasLockout && (
          <div className="flex items-center justify-between text-red-600 dark:text-red-400">
            <span className="flex items-center gap-2 text-sm">
              <Lock className="w-4 h-4" />
              Locked out ({account.blocks.lockout?.level})
            </span>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              Expires in {formatTime(ttls.lockout)}
            </span>
          </div>
        )}

        {account.blocks.rate_limit_minute?.active && ttls.minute > 0 && (
          <div className="flex items-center justify-between text-orange-600 dark:text-orange-400">
            <span className="flex items-center gap-2 text-sm">
              <Zap className="w-4 h-4" />
              Rate limited (minute)
            </span>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {account.blocks.rate_limit_minute.count}/{account.blocks.rate_limit_minute.limit} (
              {formatTime(ttls.minute)})
            </span>
          </div>
        )}

        {account.blocks.rate_limit_hour?.active && ttls.hour > 0 && (
          <div className="flex items-center justify-between text-orange-600 dark:text-orange-400">
            <span className="flex items-center gap-2 text-sm">
              <Zap className="w-4 h-4" />
              Rate limited (hour)
            </span>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {account.blocks.rate_limit_hour.count}/{account.blocks.rate_limit_hour.limit} (
              {formatTime(ttls.hour)})
            </span>
          </div>
        )}

        {hasCaptcha && (
          <div className="flex items-center gap-2 text-yellow-600 dark:text-yellow-400 text-sm">
            <Bot className="w-4 h-4" />
            CAPTCHA required
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-gray-600 dark:text-gray-400 text-sm">
            <XCircle className="w-4 h-4" />
            {account.failure_count} failed attempts
          </span>
          {account.failure_count >= 10 && (
            <span className="px-2 py-0.5 text-xs font-medium text-red-700 bg-red-100 dark:bg-red-900/30 dark:text-red-300 rounded-full">
              Possible attack
            </span>
          )}
          {account.failure_count >= 3 && account.failure_count < 5 && (
            <span className="px-2 py-0.5 text-xs font-medium text-yellow-700 bg-yellow-100 dark:bg-yellow-900/30 dark:text-yellow-300 rounded-full">
              Approaching lockout
            </span>
          )}
        </div>
      </div>

      <div className="flex gap-2 mt-4 flex-wrap">
        {hasLockout && (
          <button
            onClick={() => onClear(account.email, ['lockout'])}
            disabled={isClearing}
            className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            Clear Lockout
          </button>
        )}
        {hasRateLimit && (
          <button
            onClick={() => onClear(account.email, ['rate_limit'])}
            disabled={isClearing}
            className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            Clear Rate Limit
          </button>
        )}
        {account.failure_count > 0 && (
          <button
            onClick={() => onClear(account.email, ['failures'])}
            disabled={isClearing}
            className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            Reset Failures
          </button>
        )}
      </div>
    </div>
  );
}

// Empty State component
function EmptyState() {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 text-center">
      <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
      <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
        No auth issues
      </h3>
      <p className="text-gray-500 dark:text-gray-400">
        All users can log in without restrictions
      </p>
    </div>
  );
}

export default function AuthBlocksPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAdmin } = useAdminAuth();
  const { logout } = useAuth();
  const queryClient = useQueryClient();

  const [searchEmail, setSearchEmail] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [clearingEmail, setClearingEmail] = useState<string | null>(null);

  // Redirect if not admin
  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.push(`/login?redirect=${encodeURIComponent('/admin/ops/auth-blocks')}`);
    }
  }, [authLoading, isAdmin, router]);

  // Fetch summary stats
  const {
    data: summaryData,
    isLoading: summaryLoading,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['auth-blocks-summary'],
    queryFn: fetchSummaryStats,
    refetchInterval: 30000,
    enabled: isAdmin,
  });

  // Fetch blocked accounts
  const {
    data: accountsData,
    isLoading: accountsLoading,
    error: accountsError,
    refetch: refetchAccounts,
  } = useQuery({
    queryKey: ['auth-blocks', searchEmail, filterType],
    queryFn: () => fetchAuthIssues(searchEmail || undefined, filterType),
    refetchInterval: 30000,
    enabled: isAdmin,
  });

  // Clear blocks mutation
  const clearMutation = useMutation({
    mutationFn: ({ email, types }: { email: string; types?: string[] }) =>
      clearBlocks(email, types, 'Cleared via admin dashboard'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['auth-blocks'] });
      void queryClient.invalidateQueries({ queryKey: ['auth-blocks-summary'] });
      setClearingEmail(null);
    },
    onError: () => {
      setClearingEmail(null);
    },
  });

  const handleClear = useCallback(
    (email: string, types?: string[]) => {
      setClearingEmail(email);
      clearMutation.mutate(types ? { email, types } : { email });
    },
    [clearMutation],
  );

  const handleRefresh = useCallback(() => {
    void refetchSummary();
    void refetchAccounts();
  }, [refetchSummary, refetchAccounts]);

  const loading = authLoading || summaryLoading || accountsLoading;

  if (authLoading || (!isAdmin && !authLoading)) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
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
              <h1 className="text-xl font-semibold">Auth Blocks</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={handleRefresh}
                disabled={loading}
                className="inline-flex items-center justify-center h-9 w-9 rounded-full text-indigo-600 hover:text-white hover:bg-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/70 disabled:opacity-50"
                title="Refresh data"
              >
                <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
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

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>
          <div className="col-span-12 md:col-span-9 lg:col-span-9">
            {accountsError && (
              <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-red-700 dark:text-red-300">
                  {accountsError instanceof Error ? accountsError.message : 'An error occurred'}
                </p>
              </div>
            )}

            {/* Summary Cards */}
            {loading ? (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                {[...Array(4)].map((_, i) => (
                  <div
                    key={i}
                    className="bg-white/60 dark:bg-gray-900/40 backdrop-blur rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6"
                  >
                    <div className="animate-pulse">
                      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24 mb-2" />
                      <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-32" />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                <StatusCard
                  label="Auth Issues"
                  value={summaryData?.total_blocked ?? 0}
                  icon={AlertTriangle}
                  iconColor="text-orange-600"
                  warning
                />
                <StatusCard
                  label="Locked Out"
                  value={summaryData?.locked_out ?? 0}
                  icon={Lock}
                  iconColor="text-red-600"
                  warning
                />
                <StatusCard
                  label="Rate Limited"
                  value={summaryData?.rate_limited ?? 0}
                  icon={Zap}
                  iconColor="text-orange-600"
                  warning
                />
                <StatusCard
                  label="CAPTCHA Required"
                  value={summaryData?.captcha_required ?? 0}
                  icon={Bot}
                  iconColor="text-yellow-600"
                  warning
                />
              </div>
            )}

            {/* Search and Filter */}
            <div className="flex gap-4 mb-6">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search by email..."
                  value={searchEmail}
                  onChange={(e) => setSearchEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-500 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option value="all">All Blocks</option>
                <option value="lockout">Locked Out</option>
                <option value="rate_limit">Rate Limited</option>
                <option value="captcha">CAPTCHA Required</option>
              </select>
            </div>

            {/* Auth Issues List */}
            <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
              <div className="p-6 border-b border-gray-200/70 dark:border-gray-700/60">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5" />
                  Auth Issues
                </h3>
              </div>
              <div className="p-6">
                {loading ? (
                  <div className="space-y-4">
                    {[...Array(3)].map((_, i) => (
                      <div
                        key={i}
                        className="h-32 bg-gray-100 dark:bg-gray-700 rounded animate-pulse"
                      />
                    ))}
                  </div>
                ) : accountsData?.accounts?.length === 0 ? (
                  <EmptyState />
                ) : (
                  accountsData?.accounts?.map((account) => (
                    <BlockedAccountCard
                      key={[
                        account.email,
                        account.blocks.lockout?.ttl_seconds ?? 0,
                        account.blocks.rate_limit_minute?.ttl_seconds ?? 0,
                        account.blocks.rate_limit_hour?.ttl_seconds ?? 0,
                        account.blocks.captcha_required?.active ? '1' : '0',
                      ].join(':')}
                      account={account}
                      onClear={handleClear}
                      isClearing={clearingEmail === account.email}
                    />
                  ))
                )}
              </div>
            </div>

            <div className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
              Auto-refreshing every 30 seconds
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
