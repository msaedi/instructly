'use client';

import WeekNavigator from '@/components/availability/WeekNavigator';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';
import { useEffect, useMemo, useState } from 'react';

export default function InstructorAvailabilityPage() {
  const {
    currentWeekStart,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    weekDates,
    navigateWeek,
    setWeekSchedule,
    setMessage,
    message,
    refreshSchedule,
  } = useWeekSchedule();

  const days = weekDates;
  const [activeDay, setActiveDay] = useState(0);

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

      {/* Interactive Grid */}
      <div className="bg-white rounded-lg shadow p-4">
        <InteractiveGrid
          weekDates={weekDates}
          weekSchedule={weekSchedule}
          onScheduleChange={(s) => setWeekSchedule(s)}
          isMobile={false}
          activeDayIndex={activeDay}
          onActiveDayChange={setActiveDay}
        />
      </div>
    </div>
  );
}
