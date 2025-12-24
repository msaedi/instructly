'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { RefreshCw, Settings, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';

import BookingsTab from './components/BookingsTab';
import HistoryTab from './components/HistoryTab';
import BookingsTable from './components/BookingsTable';
import BookingDetailPanel from './components/BookingDetailPanel';
import RefundModal from './components/RefundModal';
import CancelModal from './components/CancelModal';
import AuditLogTable from './components/AuditLogTable';

import {
  type AdminBooking,
  type BookingFiltersState,
  useAdminBookings,
} from './hooks/useAdminBookings';
import { useBookingStats } from './hooks/useBookingStats';
import { type AuditFiltersState, useAuditLog } from './hooks/useAuditLog';

const defaultBookingFilters: BookingFiltersState = {
  search: '',
  status: 'all',
  payment_status: 'all',
  date_range: 'last_30_days',
  quick_filter: 'all',
  page: 1,
  per_page: 20,
};

const defaultAuditFilters: AuditFiltersState = {
  action: 'all',
  admin_id: 'all',
  date_range: 'last_30_days',
  search: '',
  page: 1,
  per_page: 20,
};

export default function PaymentsAdminClient() {
  const { isAdmin, isLoading } = useAdminAuth();
  const { logout } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const activeTab = searchParams.get('tab') === 'history' ? 'history' : 'bookings';

  const [showConfig, setShowConfig] = useState(false);
  const [bookingFilters, setBookingFilters] = useState<BookingFiltersState>(defaultBookingFilters);
  const [auditFilters, setAuditFilters] = useState<AuditFiltersState>(defaultAuditFilters);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState<AdminBooking | null>(null);
  const [refundBooking, setRefundBooking] = useState<AdminBooking | null>(null);
  const [refundOpen, setRefundOpen] = useState(false);
  const [cancelBooking, setCancelBooking] = useState<AdminBooking | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const bookingsQuery = useAdminBookings(bookingFilters);
  const statsQuery = useBookingStats();
  const auditQuery = useAuditLog(auditFilters);

  const adminOptions = useMemo(() => {
    const admins = auditQuery.data?.entries ?? [];
    const unique = new Map<string, string>();
    admins.forEach((entry) => {
      unique.set(entry.admin.id, entry.admin.email);
    });
    return [
      { value: 'all', label: 'All' },
      ...Array.from(unique.entries()).map(([id, email]) => ({ value: id, label: email })),
    ];
  }, [auditQuery.data?.entries]);

  const bookings = bookingsQuery.data?.bookings ?? [];
  const auditEntries = auditQuery.data?.entries ?? [];

  const handleTabChange = (tab: 'bookings' | 'history') => {
    const params = new URLSearchParams(searchParams.toString());
    if (tab === 'history') {
      params.set('tab', 'history');
    } else {
      params.delete('tab');
    }
    const query = params.toString();
    router.push(query ? `/admin/payments?${query}` : '/admin/payments');
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        bookingsQuery.refetch(),
        statsQuery.refetch(),
        auditQuery.refetch(),
      ]);
    } finally {
      setRefreshing(false);
    }
  };

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleToggleSelectAll = (next: boolean) => {
    if (next) {
      setSelectedIds(bookings.map((booking) => booking.id));
    } else {
      setSelectedIds([]);
    }
  };

  const handleViewDetails = (booking: AdminBooking) => {
    setSelectedBooking(booking);
    setDetailOpen(true);
  };

  const handleRefund = (booking: AdminBooking) => {
    setRefundBooking(booking);
    setRefundOpen(true);
  };

  const handleCancel = (booking: AdminBooking) => {
    setCancelBooking(booking);
    setCancelOpen(true);
  };

  const handleViewAuditLog = (booking: AdminBooking) => {
    setAuditFilters({ ...defaultAuditFilters, search: booking.id, page: 1 });
    setDetailOpen(false);
    handleTabChange('history');
  };

  const handleContact = (booking: AdminBooking, target: 'student' | 'instructor') => {
    const name = target === 'student' ? booking.student.name : booking.instructor.name;
    toast.success(`Queued email to ${name}`);
  };

  const handleMarkStatus = (booking: AdminBooking, status: 'COMPLETED' | 'NO_SHOW') => {
    toast.success(`Booking ${booking.id.slice(0, 8)} updated to ${status}`);
  };

  const handleCancelConfirm = (booking: AdminBooking, reason: string, note: string, refund: boolean) => {
    const descriptionParts = [];
    if (reason) {
      descriptionParts.push(`Reason: ${reason}`);
    }
    if (note) {
      descriptionParts.push(`Note: ${note}`);
    }
    const description = descriptionParts.length ? descriptionParts.join(' | ') : 'Reason recorded';
    toast.success(`Booking ${booking.id.slice(0, 8)} cancelled`, { description });
    if (refund) {
      toast.info('Refund will be issued once cancellation is processed.');
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
        <div className="max-w-md rounded-xl border border-gray-200 bg-white/70 p-6 text-center">
          <ShieldAlert className="h-10 w-10 mx-auto text-amber-500" aria-hidden="true" />
          <p className="mt-3 text-sm text-gray-700">You do not have access to this page.</p>
        </div>
      </div>
    );
  }

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
                <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Payments</h1>
                <p className="text-xs text-gray-500">Manage bookings, refunds, and audit history.</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleRefresh}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full text-indigo-600 hover:bg-indigo-600 hover:text-white"
              >
                <RefreshCw className={refreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
              </button>
              <button
                type="button"
                onClick={() => setShowConfig((prev) => !prev)}
                className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-100"
              >
                <Settings className="h-4 w-4" />
                {showConfig ? 'Hide Config' : 'Show Config'}
              </button>
              <button
                type="button"
                onClick={() => void logout()}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-100"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3">
            <AdminSidebar />
          </aside>
          <section className="col-span-12 md:col-span-9 space-y-6">
            {showConfig ? (
              <div className="rounded-2xl p-5 bg-indigo-50/80 ring-1 ring-indigo-200/60 text-sm text-indigo-800">
                <div className="font-semibold">Config</div>
                <p className="mt-1">Refund endpoint enabled: /api/v1/admin/bookings/:id/refund</p>
                <p className="mt-1">Additional booking APIs are in progress.</p>
              </div>
            ) : null}

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleTabChange('bookings')}
                className={
                  activeTab === 'bookings'
                    ? 'rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white'
                    : 'rounded-full px-4 py-2 text-sm font-medium text-gray-600 ring-1 ring-gray-300'
                }
              >
                Bookings
              </button>
              <button
                type="button"
                onClick={() => handleTabChange('history')}
                className={
                  activeTab === 'history'
                    ? 'rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white'
                    : 'rounded-full px-4 py-2 text-sm font-medium text-gray-600 ring-1 ring-gray-300'
                }
              >
                History
              </button>
            </div>

            {activeTab === 'bookings' ? (
              <BookingsTab
                stats={statsQuery.data}
                statsLoading={statsQuery.isFetching}
                filters={bookingFilters}
                onFiltersChange={setBookingFilters}
                table={(
                  <BookingsTable
                    bookings={bookings}
                    total={bookingsQuery.data?.total ?? 0}
                    page={bookingsQuery.data?.page ?? 1}
                    perPage={bookingsQuery.data?.per_page ?? bookingFilters.per_page}
                    totalPages={bookingsQuery.data?.total_pages ?? 1}
                    selectedIds={selectedIds}
                    onToggleSelect={handleToggleSelect}
                    onToggleSelectAll={handleToggleSelectAll}
                    onPageChange={(next) => setBookingFilters((prev) => ({ ...prev, page: next }))}
                    onViewDetails={handleViewDetails}
                    onIssueRefund={handleRefund}
                    onCancelBooking={handleCancel}
                    onContact={handleContact}
                    onMarkStatus={handleMarkStatus}
                    onViewAuditLog={handleViewAuditLog}
                  />
                )}
                bulkActions={(
                  <div className="flex items-center justify-between text-sm text-gray-500">
                    <span>Selected: {selectedIds.length}</span>
                    <button
                      type="button"
                      className="rounded-full px-4 py-2 text-xs font-medium ring-1 ring-gray-300 hover:bg-gray-100"
                    >
                      Bulk Actions
                    </button>
                  </div>
                )}
              />
            ) : (
              <HistoryTab
                filters={auditFilters}
                onFiltersChange={setAuditFilters}
                adminOptions={adminOptions}
                table={(
                  <AuditLogTable
                    entries={auditEntries}
                    summary={auditQuery.data?.summary ?? { refunds_count: 0, refunds_total: 0, captures_count: 0, captures_total: 0 }}
                    total={auditQuery.data?.total ?? 0}
                    page={auditQuery.data?.page ?? 1}
                    perPage={auditQuery.data?.per_page ?? auditFilters.per_page}
                    totalPages={auditQuery.data?.total_pages ?? 1}
                    onPageChange={(next) => setAuditFilters((prev) => ({ ...prev, page: next }))}
                  />
                )}
              />
            )}
          </section>
        </div>
      </main>

      <BookingDetailPanel
        booking={selectedBooking}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onIssueRefund={handleRefund}
        onViewAuditLog={handleViewAuditLog}
      />

      <RefundModal
        booking={refundBooking}
        open={refundOpen}
        onOpenChange={setRefundOpen}
      />

      <CancelModal
        booking={cancelBooking}
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        onConfirm={handleCancelConfirm}
      />
    </div>
  );
}
