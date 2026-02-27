// frontend/hooks/availability/usePublicAvailability.ts
/**
 * Hook for consuming the public availability endpoint.
 */

import { useState, useEffect, useCallback } from 'react';
import type { PublicInstructorAvailability, PublicTimeSlot } from '@/features/shared/api/types';

type PublicAvailability = PublicInstructorAvailability;

export function usePublicAvailability(instructorId: string, startDate?: Date) {
  const [availability, setAvailability] = useState<PublicAvailability | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAvailability = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const start = startDate || new Date();
      const end = new Date(start);
      end.setDate(end.getDate() + 30); // Add 30 days

      // Format dates as YYYY-MM-DD
      const formatDate = (date: Date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
      };

      const params = new URLSearchParams({
        start_date: formatDate(start),
        end_date: formatDate(end),
      });

      const response = await fetch(
        `/api/v1/public/instructors/${instructorId}/availability?${params}`
      );

      if (!response.ok) {
        throw new Error('Failed to fetch availability');
      }

      const data = (await response.json()) as PublicInstructorAvailability;
      setAvailability(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [instructorId, startDate]);

  useEffect(() => {
    void fetchAvailability();
  }, [fetchAvailability]);

  const getAvailableDates = (): string[] => {
    if (!availability) return [];

    const byDate = availability.availability_by_date ?? {};
    return Object.entries(byDate)
      .filter(([_, day]) => !day.is_blackout && (day.available_slots ?? []).length > 0)
      .map(([date]) => date);
  };

  const getSlotsForDate = (date: string): PublicTimeSlot[] => {
    if (!availability) return [];

    const dayInfo = availability.availability_by_date?.[date];
    return dayInfo?.available_slots ?? [];
  };

  const refresh = () => {
    void fetchAvailability();
  };

  return {
    availability,
    loading,
    error,
    getAvailableDates,
    getSlotsForDate,
    refresh,
  };
}

/**
 * Example usage in a component:
 *
 * function InstructorAvailability({ instructorId }: { instructorId: number }) {
 *   const { availability, loading, getSlotsForDate } = usePublicAvailability(instructorId);
 *
 *   if (loading) return <div>Loading...</div>;
 *
 *   return (
 *     <div>
 *       <h2>{availability?.instructor_first_name} {availability?.instructor_last_initial}.'s Availability</h2>
 *       {Object.entries(availability?.availability_by_date || {}).map(([date, dayInfo]) => (
 *         <div key={date}>
 *           <h3>{date}</h3>
 *           {dayInfo.is_blackout ? (
 *             <p>Unavailable</p>
 *           ) : (
 *             <div>
 *               {dayInfo.available_slots.map((slot, i) => (
 *                 <button key={i} onClick={() => selectSlot(date, slot)}>
 *                   {slot.start_time} - {slot.end_time}
 *                 </button>
 *               ))}
 *             </div>
 *           )}
 *         </div>
 *       ))}
 *     </div>
 *   );
 * }
 */

// THAT'S IT! No operations, no slot IDs, no complex state management.
// Just fetch and display. When booking, send instructor_id + date + times.
