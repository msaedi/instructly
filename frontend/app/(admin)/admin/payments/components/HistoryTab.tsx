import type { ReactNode } from 'react';

import { Filter, Search } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

import type { AuditFiltersState } from '../hooks/useAuditLog';
import { auditActionOptions } from '../hooks/useAuditLog';

interface HistoryTabProps {
  filters: AuditFiltersState;
  onFiltersChange: (next: AuditFiltersState) => void;
  adminOptions: { value: string; label: string }[];
  table: ReactNode;
}

const dateOptions: { value: AuditFiltersState['date_range']; label: string }[] = [
  { value: 'last_7_days', label: 'Last 7 days' },
  { value: 'last_30_days', label: 'Last 30 days' },
  { value: 'last_90_days', label: 'Last 90 days' },
  { value: 'all', label: 'All time' },
];

const quickActions: { value: AuditFiltersState['action']; label: string }[] = [
  { value: 'admin_refund', label: 'Refund' },
  { value: 'payment_capture', label: 'Capture' },
  { value: 'admin_cancel', label: 'Cancel' },
  { value: 'status_change', label: 'Status Change' },
];

export default function HistoryTab({ filters, onFiltersChange, adminOptions, table }: HistoryTabProps) {
  return (
    <div className="space-y-6">
      <div className="rounded-2xl p-6 bg-white/70 dark:bg-gray-900/50 ring-1 ring-gray-200/70 dark:ring-gray-700/60 shadow-sm">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200">
          <Filter className="h-4 w-4 text-indigo-500" />
          Filters
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-wide text-gray-500">Action</Label>
            <Select
              value={filters.action}
              onValueChange={(value) =>
                onFiltersChange({
                  ...filters,
                  action: value as AuditFiltersState['action'],
                  page: 1,
                })
              }
            >
              <SelectTrigger className="bg-white/80 border-gray-200 dark:bg-gray-900/60 dark:border-gray-700">
                <SelectValue placeholder="Action" />
              </SelectTrigger>
              <SelectContent>
                {auditActionOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-wide text-gray-500">Admin</Label>
            <Select
              value={filters.admin_id}
              onValueChange={(value) =>
                onFiltersChange({
                  ...filters,
                  admin_id: value,
                  page: 1,
                })
              }
            >
              <SelectTrigger className="bg-white/80 border-gray-200 dark:bg-gray-900/60 dark:border-gray-700">
                <SelectValue placeholder="Admin" />
              </SelectTrigger>
              <SelectContent>
                {adminOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-wide text-gray-500">Date</Label>
            <Select
              value={filters.date_range}
              onValueChange={(value) =>
                onFiltersChange({
                  ...filters,
                  date_range: value as AuditFiltersState['date_range'],
                  page: 1,
                })
              }
            >
              <SelectTrigger className="bg-white/80 border-gray-200 dark:bg-gray-900/60 dark:border-gray-700">
                <SelectValue placeholder="Date" />
              </SelectTrigger>
              <SelectContent>
                {dateOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-wide text-gray-500">Search</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <Input
                value={filters.search}
                onChange={(event) => onFiltersChange({ ...filters, search: event.target.value, page: 1 })}
                placeholder="Booking, admin, note..."
                className="pl-9 bg-white/80 border-gray-200 dark:bg-gray-900/60 dark:border-gray-700"
              />
            </div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Actions:</span>
          {quickActions.map((action) => {
            const active = filters.action === action.value;
            return (
              <button
                key={action.value}
                type="button"
                onClick={() =>
                  onFiltersChange({
                    ...filters,
                    action: active ? 'all' : action.value,
                    page: 1,
                  })
                }
                className={cn(
                  'rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition',
                  active
                    ? 'bg-indigo-600 text-white ring-indigo-400'
                    : 'bg-white/80 text-gray-700 ring-gray-200 hover:bg-indigo-50'
                )}
              >
                {action.label}
              </button>
            );
          })}
        </div>
      </div>
      {table}
    </div>
  );
}
