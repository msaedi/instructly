'use client';

import Link from 'next/link';
import { useState, useMemo } from 'react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import Modal from '@/components/Modal';
import { Download, DollarSign, Info, ArrowLeft, Calendar, Briefcase, Clock } from 'lucide-react';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';

import { useEmbedded } from '../_embedded/EmbeddedContext';
import { useInstructorEarnings } from '@/hooks/queries/useInstructorEarnings';
import { useInstructorPayouts } from '@/hooks/queries/useInstructorPayouts';

function EarningsPageImpl() {
  const embedded = useEmbedded();
  function SimpleDropdown({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: Array<{ value: string; label: string }>;
    placeholder: string;
  }) {
    const [open, setOpen] = useState(false);
    const [hovered, setHovered] = useState<string | null>(null);
    const selected = options.find((o) => o.value === value)?.label || placeholder;
    return (
      <div
        className="relative"
        tabIndex={-1}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false);
        }}
      >
        <button
          type="button"
          onClick={() => setOpen((p) => !p)}
          className="w-full h-11 rounded-lg border border-gray-300 px-3 pr-9 bg-white text-gray-800 font-medium shadow-sm focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500 flex items-center justify-between"
        >
          <span>{selected}</span>
          <svg className="w-5 h-5 text-gray-500" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.24a.75.75 0 01-1.06 0L5.25 8.29a.75.75 0 01-.02-1.08z" clipRule="evenodd" />
          </svg>
        </button>
        {open ? (
          <ul role="listbox" className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto overflow-x-hidden scrollbar-hide" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
            {options.map((opt) => (
              <li key={opt.value}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(opt.value);
                    setOpen(false);
                  }}
                  role="option"
                  aria-selected={value === opt.value}
                  onMouseEnter={() => setHovered(opt.value)}
                  onMouseLeave={() => setHovered((h) => (h === opt.value ? null : h))}
                  className={`block w-full text-left px-3 py-2 rounded-md cursor-pointer transition-colors ${
                    hovered === opt.value && opt.value !== ''
                      ? 'bg-purple-50 text-[#7E22CE]'
                      : ''
                  } ${
                    value === opt.value && opt.value !== ''
                      ? 'bg-purple-100 text-[#7E22CE] ring-1 ring-inset ring-[#D4B5F0] font-semibold'
                      : 'text-gray-800'
                  }`}
                >
                  {opt.label}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }
  const { data: earnings, isLoading: isLoadingEarnings } = useInstructorEarnings(true);
  const { data: payoutsData, isLoading: isLoadingPayouts } = useInstructorPayouts(true);
  const [activeTab, setActiveTab] = useState<'invoices' | 'payouts'>('invoices');
  const [exportOpen, setExportOpen] = useState(false);
  const [exportYear, setExportYear] = useState<string>('');
  const [exportType, setExportType] = useState<'csv' | 'pdf' | ''>('');
  const [sendingExport, setSendingExport] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);

  const years = useMemo(() => {
    const now = new Date().getFullYear();
    const start = 2025; // Earliest selectable export year
    const list: string[] = [];
    for (let y = now; y >= start; y -= 1) list.push(String(y));
    return list;
  }, []);

  const formatAmount = (value?: number) => `$${((value ?? 0) / 100).toFixed(2)}`;
  const formatCents = (value?: number | null) => `$${(((value ?? 0)) / 100).toFixed(2)}`;
  const formatInvoiceDate = (lessonDate?: string, start?: string | null) => {
    if (!lessonDate) return '—';
    const baseIso = `${lessonDate}T${start ?? '00:00:00'}`;
    const parsed = new Date(baseIso);
    if (Number.isNaN(parsed.valueOf())) return lessonDate;
    return parsed.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };
  // Use instructor-centric values from backend
  const totalLessonValue = earnings?.total_lesson_value ?? 0;
  const netEarnings = earnings?.total_earned ?? 0;
  const resolvedServiceCount = typeof earnings?.service_count === 'number'
    ? earnings.service_count
    : (typeof earnings?.booking_count === 'number' ? earnings.booking_count : 0);
  const resolvedHoursInvoiced = typeof earnings?.hours_invoiced === 'number' ? earnings.hours_invoiced : 0;
  const formatHours = (value: number) => {
    if (!Number.isFinite(value)) return '0';
    return Number.isInteger(value) ? value.toString() : value.toFixed(1);
  };
  const invoices = Array.isArray(earnings?.invoices) ? earnings!.invoices : [];
  const formatDuration = (mins?: number | null) => {
    if (!mins) return '—';
    return `${mins} min`;
  };
  const formatStatusLabel = (value?: string) => {
    if (!value) return '—';
    return value.charAt(0).toUpperCase() + value.slice(1);
  };
  const handleExport = async () => {
    if (!exportYear || sendingExport) return;
    if (!exportType) return;
    setSendingExport(true);
    const startDate = `${exportYear}-01-01`;
    const endDate = `${exportYear}-12-31`;
    try {
          const response = await fetchWithAuth('/api/v1/payments/earnings/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              start_date: startDate,
              end_date: endDate,
              format: exportType,
            }),
          });
      if (!response.ok) {
        throw new Error('Export failed');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const contentDisposition = response.headers.get('content-disposition') || '';
      const match = contentDisposition.match(/filename="?([^";]+)"?/i);
      const contentType = response.headers.get('content-type') || '';
      const resolvedExt = contentType.includes('application/pdf')
        ? 'pdf'
        : (exportType === 'pdf' ? 'pdf' : 'csv');
      const filename = match?.[1] ?? `earnings_${startDate}_${endDate}.${resolvedExt}`;
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setExportOpen(false);
    } catch (error) {
      logger.error('Export failed', error);
    } finally {
      setSendingExport(false);
    }
  };

  return (
    <div className="min-h-screen insta-dashboard-page">
      {/* Header hidden when embedded */}
      {!embedded && (
        <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4 insta-dashboard-header">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 hidden sm:block">
            <div className="container mx-auto px-8 lg:px-32 max-w-6xl pointer-events-none">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] pointer-events-auto">
                <ArrowLeft className="w-4 h-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'max-w-none px-0 lg:px-0 py-0' : 'container mx-auto px-8 lg:px-32 py-8 max-w-6xl'}>
        {!embedded && (
          <div className="sm:hidden mb-2">
            <Link href="/instructor/dashboard" aria-label="Back to dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
              <ArrowLeft className="w-5 h-5" />
              <span className="sr-only">Back to dashboard</span>
            </Link>
          </div>
        )}
        <SectionHeroCard
          id={embedded ? 'earnings-first-card' : undefined}
          icon={DollarSign}
          title="Earnings"
          subtitle="Review your payouts, exports, and lesson earnings in one place."
          actions={
            <button
              type="button"
              aria-label="How payouts work"
              onClick={() => setInfoOpen(true)}
              className="inline-flex items-center gap-1 p-2 rounded-md text-[#7E22CE] hover:bg-purple-50 transition-colors"
            >
              <Info className="w-5 h-5" />
              <span className="hidden sm:inline">More info</span>
            </button>
          }
        />

        {/* Stat Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6 mb-8">
          <div className="insta-dashboard-stat-card rounded-md sm:rounded-lg p-3 sm:p-6 h-32 sm:h-40">
            <div className="flex items-start justify-between h-full">
              <div>
                <h3 className="text-sm sm:text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1 sm:mb-2">Total Lessons</h3>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">{isLoadingEarnings ? '—' : formatAmount(totalLessonValue)}</p>
              </div>
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Calendar className="w-5 h-5 sm:w-6 sm:h-6 text-[#7E22CE]" />
              </div>
            </div>
          </div>
          <div className="insta-dashboard-stat-card rounded-md sm:rounded-lg p-3 sm:p-6 h-32 sm:h-40">
            <div className="flex items-start justify-between h-full">
              <div>
                <h3 className="text-sm sm:text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1 sm:mb-2">Net Earnings</h3>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">{isLoadingEarnings ? '—' : formatAmount(netEarnings)}</p>
              </div>
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <DollarSign className="w-5 h-5 sm:w-6 sm:h-6 text-[#7E22CE]" />
              </div>
            </div>
          </div>
          <div className="insta-dashboard-stat-card rounded-md sm:rounded-lg p-3 sm:p-6 h-32 sm:h-40">
            <div className="flex items-start justify-between h-full">
              <div>
                <h3 className="text-sm sm:text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1 sm:mb-2">Service count</h3>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">{isLoadingEarnings ? '—' : resolvedServiceCount}</p>
              </div>
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Briefcase className="w-5 h-5 sm:w-6 sm:h-6 text-[#7E22CE]" />
              </div>
            </div>
          </div>
          <div className="insta-dashboard-stat-card rounded-md sm:rounded-lg p-3 sm:p-6 h-32 sm:h-40">
            <div className="flex items-start justify-between h-full">
              <div>
                <h3 className="text-sm sm:text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1 sm:mb-2">Hours invoiced</h3>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">
                  {isLoadingEarnings ? '—' : formatHours(resolvedHoursInvoiced)}
                </p>
              </div>
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Clock className="w-5 h-5 sm:w-6 sm:h-6 text-[#7E22CE]" />
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-lg border border-gray-200 insta-surface-card">
          <div className="border-b border-gray-200 px-4 sm:px-6 pt-4">
              <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
              <button
                onClick={() => setActiveTab('invoices')}
                className={`px-2 py-2 text-xs sm:text-sm font-medium ${activeTab === 'invoices' ? 'text-[#7E22CE] border-b-2 border-[#7E22CE]' : 'text-gray-600 hover:text-[#7E22CE]'}`}
              >
                Invoices
              </button>
              <button
                onClick={() => setActiveTab('payouts')}
                className={`px-2 py-2 text-xs sm:text-sm font-medium ${activeTab === 'payouts' ? 'text-[#7E22CE] border-b-2 border-[#7E22CE]' : 'text-gray-600 hover:text-[#7E22CE]'}`}
              >
                Payouts
              </button>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setExportOpen(true)}
                  aria-label="Export transactions"
                  className="p-2 rounded-md text-[#7E22CE] hover:bg-purple-50 transition-colors"
                >
                  <Download className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
          <div className="p-4 sm:p-6">
            {activeTab === 'invoices' ? (
              invoices.length === 0 ? (
                <div className="text-sm text-gray-600">You haven&apos;t submitted any invoices yet</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead>
                      <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                        <th className="py-2 pr-4">Date</th>
                        <th className="py-2 pr-4">Student</th>
                        <th className="py-2 pr-4">Service</th>
                        <th className="py-2 pr-4">Duration</th>
                        <th className="py-2 pr-4">Lesson Price</th>
                        <th className="py-2 pr-4">Platform Fee</th>
                        <th className="py-2 pr-4">Your Earnings</th>
                        <th className="py-2 pr-4">Tip</th>
                        <th className="py-2 pr-4">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {invoices.map((invoice) => {
                        // Use backend-calculated platform fee (no frontend calculation)
                        const platformFeeRate = invoice.platform_fee_rate ?? 0;
                        const platformFeePct = Math.round(platformFeeRate * 100);
                        // Keep status mapping aligned with backend/app/constants/payment_status.py.
                        const getStatusColor = (status?: string) => {
                          switch (status) {
                            case 'authorized':
                              return 'bg-amber-50 text-amber-700';  // Pending capture
                            case 'paid':
                              return 'bg-emerald-50 text-emerald-700';  // Successfully captured
                            case 'failed':
                              return 'bg-red-50 text-red-700';  // Payment failed
                            case 'refunded':
                            case 'cancelled':
                              return 'bg-gray-50 text-gray-600';  // Reversed/cancelled
                            default:
                              return 'bg-gray-50 text-gray-600';  // Unknown status
                          }
                        };
                        const statusColor = getStatusColor(invoice.status);
                        return (
                          <tr key={`${invoice.booking_id}-${invoice.created_at}`}>
                            <td className="py-3 pr-4 text-gray-900">
                              {formatInvoiceDate(invoice.lesson_date, invoice.start_time)}
                            </td>
                            <td className="py-3 pr-4 text-gray-700">{invoice.student_name ?? 'Student'}</td>
                            <td className="py-3 pr-4 text-gray-700">{invoice.service_name ?? 'Lesson'}</td>
                            <td className="py-3 pr-4 text-gray-700">{formatDuration(invoice.duration_minutes)}</td>
                            <td className="py-3 pr-4 font-semibold text-gray-900">{formatCents(invoice.lesson_price_cents)}</td>
                            <td className="py-3 pr-4 text-gray-700">
                              {formatCents(invoice.platform_fee_cents)}
                              <span className="text-gray-400 text-xs ml-1">({platformFeePct}%)</span>
                            </td>
                            <td className="py-3 pr-4 font-semibold text-[#7E22CE]">{formatCents(invoice.instructor_share_cents)}</td>
                            <td className="py-3 pr-4 text-gray-700">{formatCents(invoice.tip_cents)}</td>
                            <td className="py-3 pr-4">
                              <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor}`}>
                                {formatStatusLabel(invoice.status)}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )
            ) : isLoadingPayouts ? (
              <div className="text-sm text-gray-600">Loading payouts...</div>
            ) : !payoutsData?.payouts || payoutsData.payouts.length === 0 ? (
              <div className="text-sm text-gray-600">
                No payouts yet. Your lesson earnings will be sent to your bank account automatically.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <div className="mb-4 flex gap-6 text-sm">
                  <div>
                    <span className="text-gray-600">Total Paid: </span>
                    <span className="font-semibold text-emerald-700">{formatCents(payoutsData.total_paid_cents)}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Pending: </span>
                    <span className="font-semibold text-amber-700">{formatCents(payoutsData.total_pending_cents)}</span>
                  </div>
                </div>
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead>
                    <tr className="text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                      <th className="py-2 pr-4">Date</th>
                      <th className="py-2 pr-4">Amount</th>
                      <th className="py-2 pr-4">Status</th>
                      <th className="py-2 pr-4">Arrival Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {payoutsData.payouts.map((payout) => {
                      const getPayoutStatusColor = (status?: string) => {
                        switch (status) {
                          case 'paid':
                            return 'bg-emerald-50 text-emerald-700';
                          case 'pending':
                          case 'in_transit':
                            return 'bg-amber-50 text-amber-700';
                          case 'failed':
                          case 'canceled':
                            return 'bg-red-50 text-red-700';
                          default:
                            return 'bg-gray-50 text-gray-600';
                        }
                      };
                      const statusColor = getPayoutStatusColor(payout.status);
                      const createdDate = new Date(payout.created_at);
                      const arrivalDate = payout.arrival_date ? new Date(payout.arrival_date) : null;
                      return (
                        <tr key={payout.id}>
                          <td className="py-3 pr-4 text-gray-900">
                            {createdDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                          </td>
                          <td className="py-3 pr-4 font-semibold text-[#7E22CE]">{formatCents(payout.amount_cents)}</td>
                          <td className="py-3 pr-4">
                            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor}`}>
                              {formatStatusLabel(payout.status)}
                            </span>
                            {payout.failure_message && (
                              <span className="ml-2 text-xs text-red-600">{payout.failure_message}</span>
                            )}
                          </td>
                          <td className="py-3 pr-4 text-gray-700">
                            {arrivalDate ? arrivalDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
      <Modal isOpen={infoOpen} onClose={() => setInfoOpen(false)} title="How payouts work" size="lg">
        <div className="space-y-5">
          <section>
            <h3 className="text-lg font-semibold text-gray-900">Payment timeline</h3>
            <p className="text-gray-700 mt-1">Payouts typically arrive in your bank account 4–8 business days after you invoice a service.</p>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-gray-900">Tips</h3>
            <p className="text-gray-700 mt-1">Students can add a tip up to 24 hours after invoice. Tips submitted after 24 hours will be included in a separate payout.</p>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-gray-900">Bulk payouts</h3>
            <p className="text-gray-700 mt-1">If you invoice more than one service in a day, you may receive a bulk payout for those services. Manual payments and tips may also be included in a bulk payout.</p>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-gray-900">Split payouts</h3>
            <p className="text-gray-700 mt-1">For services on which a student applies a discount or account credit, you may see your payment in two separate payouts.</p>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-gray-900">Sample timeline and statuses</h3>
            <div className="mt-3 divide-y divide-gray-200 rounded-lg border border-gray-200 overflow-hidden">
              <div className="grid grid-cols-[10rem_1fr] gap-3 p-3">
                <div>
                  <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-800 text-xs font-semibold inline-block">SUBMITTED</span>
                  <div className="text-xs text-gray-600">24 hours</div>
                </div>
                <div className="text-gray-700">After submission, the invoice is in review to allow the student to add a tip.</div>
              </div>
              <div className="grid grid-cols-[10rem_1fr] gap-3 p-3">
                <div>
                  <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-800 text-xs font-semibold inline-block">COLLECTING</span>
                  <div className="text-xs text-gray-600">After 24 hours</div>
                </div>
                <div className="text-gray-700">The student is charged for the service.</div>
              </div>
              <div className="grid grid-cols-[10rem_1fr] gap-3 p-3">
                <div>
                  <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-800 text-xs font-semibold inline-block">SENDING</span>
                  <div className="text-xs text-gray-600">1 business day</div>
                </div>
                <div className="text-gray-700">Stripe has successfully charged the student and is sending the payout to your bank account.</div>
              </div>
              <div className="grid grid-cols-[10rem_1fr] gap-3 p-3">
                <div>
                  <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-800 text-xs font-semibold inline-block">SENT</span>
                  <div className="text-xs text-gray-600">3–5 business days</div>
                </div>
                <div className="text-gray-700">The payout has been sent to your bank account. It may take a couple days to appear.</div>
              </div>
            </div>
          </section>
          <section>
            <h3 className="text-lg font-semibold text-gray-900">Special cases</h3>
            <div className="mt-3 space-y-3">
              <div>
                <span className="px-2 py-1 rounded-md bg-rose-100 text-rose-800 text-xs font-semibold inline-block">BANK ISSUE</span>
                <p className="text-gray-700 mt-1">There was an issue with your bank account. Please check your account settings that your bank account and routing numbers are correct.</p>
              </div>
              <div>
                <span className="px-2 py-1 rounded-md bg-rose-100 text-rose-800 text-xs font-semibold inline-block">CHARGE FAIL</span>
                <p className="text-gray-700 mt-1">If your student fails to pay for a service, click Request Payment in your invoice history and we will review.</p>
              </div>
              <div>
                <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-800 text-xs font-semibold inline-block">IN REVIEW</span>
                <p className="text-gray-700 mt-1">We&apos;re reviewing your request for payment. Please allow 5 business days.</p>
              </div>
              <div>
                <span className="px-2 py-1 rounded-md bg-emerald-100 text-emerald-800 text-xs font-semibold inline-block">PAID BY iNSTAiNSTRU</span>
                <p className="text-gray-700 mt-1">iNSTAiNSTRU may pay for the service due to the student&apos;s payment method failing.</p>
              </div>
              <div>
                <span className="px-2 py-1 rounded-md bg-rose-100 text-rose-800 text-xs font-semibold inline-block">SERVICE NOT PAID</span>
                <p className="text-gray-700 mt-1">Your request was not approved. Please reach out to support for help.</p>
              </div>
            </div>
          </section>
        </div>
      </Modal>
      <Modal
        isOpen={exportOpen}
        onClose={() => setExportOpen(false)}
        title="Export Transactions"
        size="md"
        allowOverflow
        autoHeight
        noPadding
      >
        <div className="px-5 py-4">
          <p className="text-gray-700 mb-3">Choose a time range and a file type:</p>
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Year</label>
              <SimpleDropdown
                value={exportYear}
                onChange={setExportYear}
                options={[{ value: '', label: 'Choose a year…' }, ...years.map((y) => ({ value: y, label: y }))]}
                placeholder="Choose a year…"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">File Type</label>
              <SimpleDropdown
                value={exportType}
                onChange={(v) => setExportType(v as 'csv' | 'pdf' | '')}
                options={[
                  { value: '', label: 'Choose a file type…' },
                  { value: 'csv', label: 'CSV' },
                  { value: 'pdf', label: 'PDF' },
                ]}
                placeholder="Choose a file type…"
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end">
            <button
              disabled={!exportYear || !exportType || sendingExport}
              onClick={handleExport}
              className="inline-flex items-center justify-center h-10 px-4 rounded-lg bg-[#7E22CE] text-white disabled:opacity-50 insta-primary-btn"
            >
              {sendingExport ? 'Exporting…' : 'Download Report'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default function InstructorEarningsPage() {
  return <EarningsPageImpl />;
}
