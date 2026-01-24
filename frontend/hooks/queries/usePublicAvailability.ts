import { useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';

import { publicApi } from '@/features/shared/api/client';

export interface InstructorAvailabilitySummary {
  timezone?: string;
  availabilityByDate: Record<
    string,
    {
      available_slots: Array<{ start_time: string; end_time: string }>;
      is_blackout?: boolean;
    }
  >;
}

const AVAILABILITY_STALE_TIME_MS = 1000 * 60 * 2;

const formatDate = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(
    date.getDate()
  ).padStart(2, '0')}`;

const normalizeTime = (value?: string | null) => {
  if (!value) return '00:00';
  const [h = '0', m = '0'] = value.split(':');
  return `${String(parseInt(h, 10) || 0).padStart(2, '0')}:${String(parseInt(m, 10) || 0).padStart(2, '0')}`;
};

export function usePublicAvailability(instructorIds: string[]) {
  const ids = useMemo(
    () => Array.from(new Set(instructorIds.filter((id) => typeof id === 'string' && id.length > 0))),
    [instructorIds]
  );

  const { startDate, endDate } = useMemo(() => {
    const today = new Date();
    const start = new Date(today);
    const end = new Date(start);
    end.setDate(start.getDate() + 14);
    return { startDate: formatDate(start), endDate: formatDate(end) };
  }, []);

  // Use the combine option to create a stable return value
  // The combine function only runs when the underlying query data changes
  return useQueries({
    queries: ids.map((instructorId) => ({
      queryKey: ['availability', 'public', instructorId, startDate, endDate],
      staleTime: AVAILABILITY_STALE_TIME_MS,
      enabled: Boolean(instructorId),
      queryFn: async (): Promise<InstructorAvailabilitySummary | null> => {
        const response = await publicApi.getInstructorAvailability(instructorId, {
          start_date: startDate,
          end_date: endDate,
        });

        if (response.error || response.status !== 200 || !response.data) {
          return null;
        }

        const byDate = response.data.availability_by_date || {};
        const normalizedEntries = Object.entries(byDate).reduce<
          Record<string, { available_slots: Array<{ start_time: string; end_time: string }>; is_blackout?: boolean }>
        >((acc, [date, day]) => {
          if (!day) return acc;
          acc[date] = {
            available_slots: (day.available_slots || []).map((slot) => ({
              start_time: normalizeTime(slot.start_time),
              end_time: normalizeTime(slot.end_time),
            })),
            is_blackout: day.is_blackout,
          };
          return acc;
        }, {});

        return {
          timezone: response.data.timezone ?? undefined,
          availabilityByDate: normalizedEntries,
        };
      },
    })),
    combine: (results) => {
      const availabilityByInstructor: Record<string, InstructorAvailabilitySummary> = {};
      results.forEach((result, index) => {
        const data = result.data;
        const instructorId = ids[index];
        if (!instructorId || !data) return;
        availabilityByInstructor[instructorId] = data;
      });
      return availabilityByInstructor;
    },
  });
}
