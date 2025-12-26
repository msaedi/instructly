import type { ReactNode } from 'react';

import type { BookingFiltersState } from '../hooks/useAdminBookings';
import type { BookingStats } from '../hooks/useBookingStats';
import QuickStats from './QuickStats';
import BookingFilters from './BookingFilters';

interface BookingsTabProps {
  stats: BookingStats | undefined;
  statsLoading: boolean;
  filters: BookingFiltersState;
  onFiltersChange: (next: BookingFiltersState) => void;
  table: ReactNode;
  bulkActions: ReactNode;
}

export default function BookingsTab({
  stats,
  statsLoading,
  filters,
  onFiltersChange,
  table,
  bulkActions,
}: BookingsTabProps) {
  return (
    <div className="space-y-6">
      <QuickStats stats={stats} isLoading={statsLoading} />
      <BookingFilters filters={filters} onChange={onFiltersChange} />
      {table}
      {bulkActions}
    </div>
  );
}
