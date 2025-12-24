import { useQuery } from '@tanstack/react-query';

import type {
  AdminAuditEntry,
  AdminAuditLogResponse,
  ListAdminAuditLogApiV1AdminAuditLogGetParams,
} from '@/src/api/generated/instructly.schemas';
import { listAdminAuditLogApiV1AdminAuditLogGet } from '@/src/api/generated/admin-bookings/admin-bookings';

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

const ACTION_VALUES: AuditAction[] = [
  'admin_refund',
  'payment_capture',
  'admin_cancel',
  'status_change',
];

const toDateParam = (value: Date) => value.toISOString().slice(0, 10);

const resolveDateRange = (range: AuditFiltersState['date_range']) => {
  if (range === 'all') {
    return { dateFrom: null, dateTo: null };
  }
  const now = new Date();
  const days = range === 'last_7_days' ? 7 : range === 'last_30_days' ? 30 : 90;
  const start = new Date(now);
  start.setDate(now.getDate() - days);
  return { dateFrom: toDateParam(start), dateTo: toDateParam(now) };
};

const extractNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
};

const parseAuditDetails = (details: AdminAuditEntry['details']) => {
  const amountCents = extractNumber(details?.['amount_cents']);
  const amount = amountCents !== null ? amountCents / 100 : 0;
  const reason = typeof details?.['reason'] === 'string' ? details['reason'] : undefined;
  const note = typeof details?.['note'] === 'string' ? details['note'] : undefined;
  return { amount, reason, note };
};

const mapAuditEntry = (entry: AdminAuditEntry): AuditEntry => {
  const action = ACTION_VALUES.includes(entry.action as AuditAction)
    ? (entry.action as AuditAction)
    : 'status_change';
  const { amount, reason, note } = parseAuditDetails(entry.details);
  const mapped: AuditEntry = {
    id: entry.id,
    timestamp: entry.timestamp,
    admin: entry.admin,
    action,
    booking_id: entry.resource_id,
    amount,
  };
  if (reason) {
    mapped.reason = reason;
  }
  if (note) {
    mapped.note = note;
  }
  return mapped;
};

const applySearchFilter = (entries: AuditEntry[], search: string) => {
  const needle = search.trim().toLowerCase();
  if (!needle) {
    return entries;
  }
  return entries.filter((entry) => {
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
    return haystack.includes(needle);
  });
};

export function useAuditLog(filters: AuditFiltersState) {
  return useQuery({
    queryKey: ['admin-payments', 'audit', filters],
    queryFn: async (): Promise<AuditLogResponse> => {
      const params: ListAdminAuditLogApiV1AdminAuditLogGetParams = {
        page: filters.page,
        per_page: filters.per_page,
      };

      if (filters.action !== 'all') {
        params.action = [filters.action];
      }

      if (filters.admin_id !== 'all') {
        params.admin_id = filters.admin_id;
      }

      const { dateFrom, dateTo } = resolveDateRange(filters.date_range);
      if (dateFrom) {
        params.date_from = dateFrom;
      }
      if (dateTo) {
        params.date_to = dateTo;
      }

      const response: AdminAuditLogResponse = await listAdminAuditLogApiV1AdminAuditLogGet(params);
      let entries = response.entries.map(mapAuditEntry);
      entries = applySearchFilter(entries, filters.search);

      const total = filters.search.trim() ? entries.length : response.total;
      const totalPages = filters.search.trim()
        ? Math.max(1, Math.ceil(total / filters.per_page))
        : response.total_pages;

      return {
        entries,
        summary: response.summary,
        total,
        page: response.page,
        per_page: response.per_page,
        total_pages: totalPages,
      };
    },
  });
}
