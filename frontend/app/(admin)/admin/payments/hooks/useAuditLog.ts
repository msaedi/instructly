import { useQuery } from '@tanstack/react-query';

export type AuditAction = 'admin_refund' | 'payment_capture' | 'admin_cancel' | 'status_change';

export interface AuditActor {
  id: string;
  email: string;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  admin: AuditActor;
  action: AuditAction;
  booking_id: string;
  amount: number;
  reason?: string;
  note?: string;
}

export interface AuditSummary {
  refunds_count: number;
  refunds_total: number;
  captures_count: number;
  captures_total: number;
}

export interface AuditFiltersState {
  action: 'all' | AuditAction;
  admin_id: 'all' | string;
  date_range: 'last_7_days' | 'last_30_days' | 'last_90_days' | 'all';
  search: string;
  page: number;
  per_page: number;
}

export interface AuditLogResponse {
  entries: AuditEntry[];
  summary: AuditSummary;
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export const auditActionOptions: { value: AuditFiltersState['action']; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'admin_refund', label: 'Refund' },
  { value: 'payment_capture', label: 'Capture' },
  { value: 'admin_cancel', label: 'Cancel' },
  { value: 'status_change', label: 'Status change' },
];

const MOCK_ENTRIES: AuditEntry[] = [
  {
    id: 'audit_01',
    timestamp: '2025-12-24T15:45:00Z',
    admin: { id: 'admin_01', email: 'admin@instainstru.com' },
    action: 'admin_refund',
    booking_id: 'bk_01HQXYZ123ABC',
    amount: 134.4,
    reason: 'Instructor no-show',
    note: 'Student reported instructor did not show up',
  },
  {
    id: 'audit_02',
    timestamp: '2025-12-24T14:30:00Z',
    admin: { id: 'system', email: 'system' },
    action: 'payment_capture',
    booking_id: 'bk_01HQDEF456JKL',
    amount: 90,
    note: 'Auto-captured after 24h',
  },
  {
    id: 'audit_03',
    timestamp: '2025-12-23T16:00:00Z',
    admin: { id: 'admin_02', email: 'ops@instainstru.com' },
    action: 'admin_cancel',
    booking_id: 'bk_01HQJKL012PQR',
    amount: 120,
    reason: 'Platform error',
    note: 'Duplicate booking created by bug',
  },
];

const MOCK_SUMMARY: AuditSummary = {
  refunds_count: 12,
  refunds_total: 1420,
  captures_count: 45,
  captures_total: 5280,
};

function filterByDateRange(date: Date, range: AuditFiltersState['date_range']) {
  if (range === 'all') {
    return true;
  }
  const now = new Date();
  const cutoff = new Date(now);
  const days = range === 'last_7_days' ? 7 : range === 'last_30_days' ? 30 : 90;
  cutoff.setDate(now.getDate() - days);
  return date >= cutoff;
}

function applyAuditFilters(entries: AuditEntry[], filters: AuditFiltersState) {
  const search = filters.search.trim().toLowerCase();
  return entries.filter((entry) => {
    if (search) {
      const haystack = [
        entry.id,
        entry.booking_id,
        entry.admin.email,
        entry.action,
        entry.reason ?? '',
        entry.note ?? '',
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(search)) {
        return false;
      }
    }

    if (filters.action !== 'all' && entry.action !== filters.action) {
      return false;
    }

    if (filters.admin_id !== 'all' && entry.admin.id !== filters.admin_id) {
      return false;
    }

    const entryDate = new Date(entry.timestamp);
    if (!filterByDateRange(entryDate, filters.date_range)) {
      return false;
    }

    return true;
  });
}

export function useAuditLog(filters: AuditFiltersState) {
  return useQuery({
    queryKey: ['admin-payments', 'audit', filters],
    queryFn: async (): Promise<AuditLogResponse> => {
      const filtered = applyAuditFilters(MOCK_ENTRIES, filters);
      const total = filtered.length;
      const totalPages = Math.max(1, Math.ceil(total / filters.per_page));
      const start = (filters.page - 1) * filters.per_page;
      const entries = filtered.slice(start, start + filters.per_page);
      return {
        entries,
        summary: MOCK_SUMMARY,
        total,
        page: filters.page,
        per_page: filters.per_page,
        total_pages: totalPages,
      };
    },
  });
}
