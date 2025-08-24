'use client';

import WeekNavigator from '@/components/availability/WeekNavigator';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';
import { useAvailabilityOperations } from '@/legacy-patterns/useAvailabilityOperations';
import { useBookedSlots } from '@/hooks/availability/useBookedSlots';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/queries/useAuth';
import { AVAILABILITY_CONSTANTS } from '@/types/availability';

export default function InstructorAvailabilityPage() {
  const { user } = useAuth();
  const {
    currentWeekStart,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    existingSlots,
    weekDates,
    navigateWeek,
    setWeekSchedule,
    setMessage,
    message,
    refreshSchedule,
  } = useWeekSchedule();

  const days = weekDates;
  const [activeDay, setActiveDay] = useState(0);
  const [saveInfo, setSaveInfo] = useState<string | null>(null);
  const [repeatWeeks, setRepeatWeeks] = useState<number>(4);
  const [isMobile, setIsMobile] = useState(false);
  const [startHour, setStartHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_START_HOUR);
  const [endHour, setEndHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_END_HOUR);

  useEffect(() => {
    const mq = () => window.matchMedia('(max-width: 640px)').matches;
    const update = () => setIsMobile(mq());
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  // Booked slots (for future booking guard and preserving)
  const {
    bookedSlots,
    fetchBookedSlots,
    refreshBookings,
  } = useBookedSlots();

  useEffect(() => {
    if (!isLoading) {
      fetchBookedSlots(currentWeekStart);
    }
  }, [currentWeekStart, isLoading, fetchBookedSlots]);

  const {
    isSaving,
    saveWeekSchedule,
    applyToFutureWeeks,
  } = useAvailabilityOperations({
    weekSchedule,
    savedWeekSchedule,
    currentWeekStart,
    existingSlots,
    bookedSlots,
    weekDates,
    onSaveSuccess: async () => {
      await refreshSchedule();
      await refreshBookings(currentWeekStart);
      setSaveInfo('Saved');
      setTimeout(() => setSaveInfo(null), 2000);
    },
    onScheduleUpdate: (newSchedule) => setWeekSchedule(newSchedule),
  });

  const updateSlot = (date: string, start: string, end: string) => {
    setWeekSchedule((prev) => {
      const existing = prev[date] || [];
      return { ...prev, [date]: [...existing, { start_time: start, end_time: end }] };
    });
  };

  const removeSlot = (date: string, idx: number) => {
    setWeekSchedule((prev) => {
      const existing = prev[date] || [];
      const next = existing.slice();
      next.splice(idx, 1);
      const out = { ...prev } as any;
      if (next.length === 0) delete out[date];
      else out[date] = next;
      return out;
    });
  };

  function formatHour(h: number): string {
    const period = h >= 12 ? 'PM' : 'AM';
    const disp = h % 12 || 12;
    return `${disp}:00 ${period}`;
  }

  useEffect(() => {
    if (message?.type === 'success') {
      const timer = setTimeout(() => setMessage(null), 2500);
      return () => clearTimeout(timer);
    }
  }, [message, setMessage]);

  const header = useMemo(() => (
    <WeekNavigator
      currentWeekStart={currentWeekStart}
      onNavigate={navigateWeek}
      hasUnsavedChanges={hasUnsavedChanges}
      disabled={isLoading}
    />
  ), [currentWeekStart, navigateWeek, hasUnsavedChanges, isLoading]);

  return (
    <div className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-[#6A0DAD]">Availability</h1>
      <p className="text-gray-600 mt-1">Set the times you’re available to teach.</p>

      {header}

      {/* Actions (top of grid) */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* Repeat dropdown */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-700">Repeat this schedule:</span>
          <select
            className="border border-gray-300 rounded-md px-2 py-1 text-sm"
            value={repeatWeeks}
            onChange={(e) => setRepeatWeeks(parseInt(e.target.value, 10))}
          >
            {[1,2,3,4,6,8,12].map((w) => (
              <option key={w} value={w}>{w} weeks</option>
            ))}
          </select>
        </div>

        <button
          disabled={isSaving || !hasUnsavedChanges}
          onClick={async () => {
            const result = await saveWeekSchedule({ skipValidation: false });
            if (!result.success) {
              toast.error(result.message || 'Failed to save');
              return;
            }
            toast.success('Availability saved');
          }}
          className={`px-4 py-2 rounded-md text-white ${hasUnsavedChanges ? 'bg-[#6A0DAD] hover:bg-[#5a0c94]' : 'bg-gray-300 cursor-not-allowed'}`}
        >
          {isSaving ? 'Saving…' : hasUnsavedChanges ? 'Save changes' : 'Saved'}
        </button>
        <button
          onClick={async () => {
            const end = new Date(currentWeekStart);
            end.setDate(end.getDate() + repeatWeeks * 7);
            const endISO = `${end.getFullYear()}-${String(end.getMonth()+1).padStart(2,'0')}-${String(end.getDate()).padStart(2,'0')}`;
            const res = await applyToFutureWeeks(endISO);
            if (!res.success) {
              toast.error(res.message || 'Failed to apply to future weeks');
              return;
            }
            toast.success(`Applied through ${endISO}`);
          }}
          className="px-3 py-2 rounded-md border border-gray-300 text-sm text-gray-700 hover:bg-gray-50"
        >
          Apply
        </button>

        {/* Hour range controls */}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-sm text-gray-700">Hours:</span>
          <select
            className="border border-gray-300 rounded-md px-2 py-1 text-sm"
            value={startHour}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              setStartHour(v);
              if (v >= endHour) setEndHour(Math.min(v + 1, 23));
            }}
          >
            {Array.from({ length: 24 }, (_, h) => h)
              .map((h) => (
                <option key={h} value={h}>{formatHour(h)}</option>
              ))}
          </select>
          <span className="text-gray-500">to</span>
          <select
            className="border border-gray-300 rounded-md px-2 py-1 text-sm"
            value={endHour}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              setEndHour(v);
              if (v <= startHour) setStartHour(Math.max(v - 1, 0));
            }}
          >
            {Array.from({ length: 24 }, (_, h) => h)
              .map((h) => (
                <option key={h} value={h}>{formatHour(h)}</option>
              ))}
          </select>
        </div>
      </div>

      {/* Mobile day chips */}
      {isMobile && (
        <div className="mb-3 flex gap-2 overflow-x-auto">
          {weekDates.map((d, i) => (
            <button
              key={d.fullDate}
              onClick={() => setActiveDay(i)}
              className={`px-3 py-2 rounded-full text-sm border ${i === activeDay ? 'bg-[#6A0DAD] text-white border-[#6A0DAD]' : 'bg-white text-gray-700 border-gray-300'}`}
            >
              {d.date.toLocaleDateString('en-US', { weekday: 'short' })}
            </button>
          ))}
        </div>
      )}

      {/* Interactive Grid */}
      <div className="bg-white rounded-lg shadow p-4">
        <InteractiveGrid
          weekDates={weekDates}
          weekSchedule={weekSchedule}
          bookedSlots={bookedSlots}
          onScheduleChange={(s) => setWeekSchedule(s)}
          isMobile={isMobile}
          activeDayIndex={activeDay}
          onActiveDayChange={setActiveDay}
          timezone={(user as any)?.timezone}
          startHour={startHour}
          endHour={endHour}
        />
      </div>


    </div>
  );
}
