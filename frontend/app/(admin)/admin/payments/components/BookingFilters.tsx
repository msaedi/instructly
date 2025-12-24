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

import type { BookingFiltersState } from '../hooks/useAdminBookings';
import { bookingStatusOptions, dateRangeOptions, paymentStatusOptions } from '../hooks/useAdminBookings';

interface BookingFiltersProps {
  filters: BookingFiltersState;
  onChange: (next: BookingFiltersState) => void;
}

const quickFilters: { value: BookingFiltersState['quick_filter']; label: string }[] = [
  { value: 'needs_action', label: 'Needs Action' },
  { value: 'disputed', label: 'Disputed' },
  { value: 'refunded', label: 'Refunded' },
];

export default function BookingFilters({ filters, onChange }: BookingFiltersProps) {
  return (
    <div className="rounded-2xl p-6 bg-white/70 dark:bg-gray-900/50 ring-1 ring-gray-200/70 dark:ring-gray-700/60 shadow-sm space-y-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200">
        <Filter className="h-4 w-4 text-indigo-500" />
        Search & Filter
      </div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative w-full lg:max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <Input
            value={filters.search}
            onChange={(event) => onChange({ ...filters, search: event.target.value, page: 1 })}
            placeholder="Search booking ID, student, instructor..."
            className="pl-9 bg-white/80 dark:bg-gray-900/60 border-gray-200 dark:border-gray-700"
          />
        </div>
        <div className="grid gap-3 md:grid-cols-3 lg:flex lg:items-center lg:gap-4">
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-wide text-gray-500">Status</Label>
            <Select
              value={filters.status}
              onValueChange={(value) =>
                onChange({ ...filters, status: value as BookingFiltersState['status'], page: 1 })
              }
            >
              <SelectTrigger className="bg-white/80 dark:bg-gray-900/60 border-gray-200 dark:border-gray-700">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                {bookingStatusOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs uppercase tracking-wide text-gray-500">Payment</Label>
            <Select
              value={filters.payment_status}
              onValueChange={(value) =>
                onChange({
                  ...filters,
                  payment_status: value as BookingFiltersState['payment_status'],
                  page: 1,
                })
              }
            >
              <SelectTrigger className="bg-white/80 dark:bg-gray-900/60 border-gray-200 dark:border-gray-700">
                <SelectValue placeholder="Payment" />
              </SelectTrigger>
              <SelectContent>
                {paymentStatusOptions.map((option) => (
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
                onChange({
                  ...filters,
                  date_range: value as BookingFiltersState['date_range'],
                  page: 1,
                })
              }
            >
              <SelectTrigger className="bg-white/80 dark:bg-gray-900/60 border-gray-200 dark:border-gray-700">
                <SelectValue placeholder="Date" />
              </SelectTrigger>
              <SelectContent>
                {dateRangeOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-gray-500">Quick filters:</span>
        {quickFilters.map((filter) => {
          const active = filters.quick_filter === filter.value;
          return (
            <button
              key={filter.value}
              type="button"
              onClick={() =>
                onChange({
                  ...filters,
                  quick_filter: active ? 'all' : filter.value,
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
              {filter.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
