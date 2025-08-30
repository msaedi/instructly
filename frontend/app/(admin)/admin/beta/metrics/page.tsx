'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { getPerformanceMetrics, type MetricsPerformanceResponse } from '@/lib/betaApi';
import { logger } from '@/lib/logger';

export default function BetaMetricsPage() {
  const { isAdmin, isLoading } = useAdminAuth();
  const { logout } = useAuth();
  const [data, setData] = useState<MetricsPerformanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await getPerformanceMetrics();
        if (mounted) setData(res);
      } catch (e) {
        logger.error('Failed to fetch metrics', e);
        setError('Failed to load metrics');
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  if (isLoading) return null;
  if (!isAdmin) return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
      <div className="text-center text-sm text-gray-600 dark:text-gray-300">You do not have access to this page.</div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">iNSTAiNSTRU</Link>
              <h1 className="text-xl font-semibold">Beta Metrics</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button onClick={logout} className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer">Log out</button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>
          <section className="col-span-12 md:col-span-9 lg:col-span-9">
            <div className="mb-6">
              <p className="text-sm text-gray-500">Basic service metrics and recent performance.</p>
            </div>

            {loading && <div className="text-sm text-gray-500">Loading...</div>}
            {error && <div className="text-sm text-red-600">{error}</div>}
            {!loading && !error && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <MetricsCard title="Availability Service" data={data?.availability_service} />
                <MetricsCard title="Booking Service" data={data?.booking_service} />
                <MetricsCard title="Conflict Checker" data={data?.conflict_checker} />
                <MetricsCard title="System" data={data?.system} />
                <MetricsCard title="Database" data={data?.database} />
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function MetricsCard({ title, data }: { title: string; data: any }) {
  return (
    <div className="rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur p-4">
      <h2 className="text-sm font-semibold mb-2">{title}</h2>
      <pre className="text-xs overflow-x-auto whitespace-pre-wrap break-words">{JSON.stringify(data ?? {}, null, 2)}</pre>
    </div>
  );
}
