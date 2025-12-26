import type { AuditEntry, AuditSummary } from '../hooks/useAuditLog';
import { formatCurrency, formatDateTime } from '../utils';

interface AuditLogTableProps {
  entries: AuditEntry[];
  summary: AuditSummary;
  total: number;
  page: number;
  perPage: number;
  totalPages: number;
  onPageChange: (next: number) => void;
}

const actionLabels: Record<string, string> = {
  admin_refund: 'REFUND',
  payment_capture: 'CAPTURE',
  admin_cancel: 'CANCEL',
  status_change: 'STATUS CHANGE',
};

export default function AuditLogTable({
  entries,
  summary,
  total,
  page,
  perPage,
  totalPages,
  onPageChange,
}: AuditLogTableProps) {
  const rangeStart = total === 0 ? 0 : (page - 1) * perPage + 1;
  const rangeEnd = Math.min(total, page * perPage);

  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-white/70 dark:bg-gray-900/50 ring-1 ring-gray-200/70 dark:ring-gray-700/60 shadow-sm overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-gray-500">
            <tr className="border-b border-gray-200/70 dark:border-gray-700/60">
              <th className="px-4 py-3 text-left">Time</th>
              <th className="px-4 py-3 text-left">Admin</th>
              <th className="px-4 py-3 text-left">Action</th>
              <th className="px-4 py-3 text-left">Booking</th>
              <th className="px-4 py-3 text-left">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200/70 dark:divide-gray-700/60">
            {entries.map((entry) => (
              <tr key={entry.id} className="hover:bg-gray-50/70 dark:hover:bg-gray-800/40">
                <td className="px-4 py-4 text-gray-700">
                  <div className="font-medium text-gray-900">{formatDateTime(entry.timestamp)}</div>
                </td>
                <td className="px-4 py-4">
                  <div className="text-sm text-gray-700">{entry.admin.email}</div>
                </td>
                <td className="px-4 py-4">
                  <div className="font-semibold text-indigo-700">{actionLabels[entry.action]}</div>
                  {entry.reason ? (
                    <div className="text-xs text-gray-500">Reason: {entry.reason}</div>
                  ) : null}
                  {entry.note ? (
                    <div className="text-xs text-gray-500">Note: &quot;{entry.note}&quot;</div>
                  ) : null}
                </td>
                <td className="px-4 py-4 text-gray-700">{entry.booking_id}</td>
                <td className="px-4 py-4 text-gray-700">{formatCurrency(entry.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-gray-500">
        <div>
          Showing {rangeStart}-{rangeEnd} of {total}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="rounded-full px-3 py-1 text-xs font-medium ring-1 ring-gray-300 disabled:opacity-40"
          >
            Prev
          </button>
          <span className="text-xs">Page {page} of {totalPages}</span>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="rounded-full px-3 py-1 text-xs font-medium ring-1 ring-gray-300 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
      <div className="text-sm text-gray-600">
        Summary: {summary.refunds_count} refunds ({formatCurrency(summary.refunds_total)}) |{' '}
        {summary.captures_count} captures ({formatCurrency(summary.captures_total)}) this month
      </div>
    </div>
  );
}
