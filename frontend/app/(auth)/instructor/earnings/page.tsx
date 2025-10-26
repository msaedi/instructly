'use client';

import Link from 'next/link';
import { useEffect, useState, useCallback, useMemo } from 'react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { protectedApi } from '@/features/shared/api/client';
import Modal from '@/components/Modal';
import { Download, DollarSign, Info, ArrowLeft } from 'lucide-react';

export default function InstructorEarningsPage(props?: { embedded?: boolean }) {
  const embedded = Boolean(props?.embedded);
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
  const [serviceCount, setServiceCount] = useState<number>(0);
  const [hoursInvoiced, setHoursInvoiced] = useState<number>(0);
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

  // Fetch services count
  useEffect(() => {
    (async () => {
      try {
        const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
        if (res.ok) {
          const data = await res.json();
          const count = Array.isArray(data?.services) ? data.services.length : 0;
          setServiceCount(count);
        }
      } catch {
        setServiceCount(0);
      }
    })();
  }, []);

  // Compute hours from completed bookings (best-effort)
  const parseTimeToMinutes = useCallback((t: string): number => {
    const [h, m] = String(t || '').split(':');
    const hh = parseInt(h || '0', 10);
    const mm = parseInt(m || '0', 10);
    return (Number.isFinite(hh) ? hh : 0) * 60 + (Number.isFinite(mm) ? mm : 0);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await protectedApi.getBookings({ status: 'completed', limit: 200 });
        const items = (resp.data as unknown as { items?: Array<{ start_time?: string; end_time?: string }> })?.items || [];
        let mins = 0;
        for (const b of items) {
          mins += Math.max(0, parseTimeToMinutes(b?.end_time || '0:0') - parseTimeToMinutes(b?.start_time || '0:0'));
        }
        if (!cancelled) setHoursInvoiced(Math.round(mins / 60));
      } catch {
        if (!cancelled) setHoursInvoiced(0);
      }
    })();
    return () => { cancelled = true; };
  }, [parseTimeToMinutes]);

  return (
    <div className="min-h-screen">
      {/* Header hidden when embedded */}
      {!embedded && (
        <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
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
        {/* Title card hidden when embedded; first visible card anchor */}
        {!embedded && (
          <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
            <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <DollarSign className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-800">Earnings</h1>
                <p className="text-sm text-gray-600">Your payouts and earnings summary will appear here.</p>
              </div>
            </div>
            <button
              type="button"
              aria-label="How payouts work"
              onClick={() => setInfoOpen(true)}
              className="inline-flex items-center gap-1 p-2 rounded-md text-[#7E22CE] hover:bg-purple-50 transition-colors"
            >
              <Info className="w-5 h-5" />
              <span className="hidden sm:inline">More info</span>
            </button>
          </div>
        </div>
        )}

        {/* Stat Cards */}
        <div id={embedded ? 'earnings-first-card' : undefined} className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6 mb-8">
          <div className="bg-white rounded-lg border border-gray-200 p-5 sm:p-6">
            <h3 className="text-xs sm:text-sm font-medium text-gray-600 tracking-wide mb-2 uppercase">Total earned</h3>
            <p className="text-3xl font-bold text-[#7E22CE] uppercase">$0</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-5 sm:p-6">
            <h3 className="text-xs sm:text-sm font-medium text-gray-600 tracking-wide mb-2 uppercase">Sent to bank</h3>
            <p className="text-3xl font-bold text-[#7E22CE] uppercase">$0</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-5 sm:p-6">
            <h3 className="text-xs sm:text-sm font-medium text-gray-600 tracking-wide mb-2 uppercase">Service count</h3>
            <p className="text-3xl font-bold text-[#7E22CE] uppercase">{serviceCount}</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-5 sm:p-6">
            <h3 className="text-xs sm:text-sm font-medium text-gray-600 tracking-wide mb-2 uppercase">Hours invoiced</h3>
            <p className="text-3xl font-bold text-[#7E22CE] uppercase">{hoursInvoiced}</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-lg border border-gray-200">
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
              <div className="text-sm text-gray-600">You haven&apos;t submitted any invoices yet</div>
            ) : (
              <div className="text-sm text-gray-600">No payouts yet.</div>
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
      <Modal isOpen={exportOpen} onClose={() => setExportOpen(false)} title="Export Transactions" size="md">
        <div className="p-2 sm:p-0">
          <p className="text-gray-700 mb-4">Choose a time range and a file type:</p>
          <div className="space-y-4">
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
          <div className="mt-6 flex justify-end">
            <button
              disabled={!exportYear || !exportType || sendingExport}
              onClick={async () => {
                setSendingExport(true);
                try {
                  // Placeholder: wire to backend export endpoint when available
                  // e.g., await fetchWithAuth(`/api/payments/exports?year=${exportYear}&type=${exportType}`)
                  setTimeout(() => {}, 300);
                  setExportOpen(false);
                } finally {
                  setSendingExport(false);
                }
              }}
              className="inline-flex items-center justify-center h-10 px-4 rounded-lg bg-[#7E22CE] text-white disabled:opacity-50"
            >
              {sendingExport ? 'Sending…' : 'Send to my Email'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
