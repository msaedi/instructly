'use client';

import WeekNavigator from '@/components/availability/WeekNavigator';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import { useAvailability } from '@/hooks/availability/useAvailability';
import { useBookedSlots } from '@/hooks/availability/useBookedSlots';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/queries/useAuth';
import { AVAILABILITY_CONSTANTS } from '@/types/availability';
import { UserData } from '@/types/user';
import { getWeekDates } from '@/lib/availability/dateHelpers';

export default function InstructorAvailabilityPage() {
  const { user } = useAuth();
  const userData = user as unknown as UserData;
  const {
    currentWeekStart,
    weekSchedule,
    hasUnsavedChanges,
    isLoading,
    weekDates,
    navigateWeek,
    setWeekSchedule,
    setMessage,
    message,
    refreshSchedule,
    version,
    lastModified,
    saveWeek,
    applyToFutureWeeks,
  } = useAvailability();

  const [activeDay, setActiveDay] = useState(0);
  const [repeatWeeks, setRepeatWeeks] = useState<number>(4);
  const [isMobile, setIsMobile] = useState(false);
  const [startHour, setStartHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_START_HOUR);
  const [endHour, setEndHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_END_HOUR);
  const [showConflictModal, setShowConflictModal] = useState(false);
  const [lastUpdatedLocal, setLastUpdatedLocal] = useState<string | null>(null);
  const [modalFocusTrap, setModalFocusTrap] = useState<HTMLDivElement | null>(null);

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
  } = useBookedSlots();

  useEffect(() => {
    if (!isLoading) {
      fetchBookedSlots(currentWeekStart);
    }
  }, [currentWeekStart, isLoading, fetchBookedSlots]);

  const isSaving = false;

  // Convert Date[] from hook to WeekDateInfo[] for components
  const weekDateInfo = useMemo(() => getWeekDates(currentWeekStart), [currentWeekStart]);

  // Update a user-friendly local timestamp from Last-Modified (server) or version fallback
  useEffect(() => {
    if (lastModified) {
      // Let browser parse and render in local timezone
      const d = new Date(lastModified);
      if (!isNaN(d.getTime())) setLastUpdatedLocal(d.toLocaleString());
      else setLastUpdatedLocal(new Date().toLocaleString());
    } else if (version) {
      setLastUpdatedLocal(new Date().toLocaleString());
    }
  }, [lastModified, version]);

  // Handle ESC to close modal when open
  useEffect(() => {
    if (!showConflictModal) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowConflictModal(false);
      if (e.key === 'Tab' && modalFocusTrap) {
        // Simple focus trap: keep focus within modal
        const focusable = modalFocusTrap.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!first || !last) return;
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey) {
          if (active === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (active === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [showConflictModal, modalFocusTrap]);


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
      <p className="text-xs text-gray-500 mt-1">Last updated: <span className="font-mono">{lastUpdatedLocal || '—'}</span></p>

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
            const result = await saveWeek({ clearExisting: true });
            if (!result.success) {
              if (result.code === 409) {
                setShowConflictModal(true);
              } else {
                toast.error(result.message || 'Failed to save');
              }
              return;
            }
            toast.success('Availability saved');
            setLastUpdatedLocal(new Date().toLocaleString());
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

      {showConflictModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-labelledby="conflict-title" aria-describedby="conflict-desc">
          <div className="absolute inset-0 bg-black/30" onClick={() => setShowConflictModal(false)}></div>
          <div
            className="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-sm"
            ref={setModalFocusTrap}
          >
            <h3 id="conflict-title" className="text-lg font-semibold text-gray-900">Schedule changed</h3>
            <p id="conflict-desc" className="text-sm text-gray-600 mt-2">This week was updated in another tab or device. Refresh to load the latest snapshot?</p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="px-4 py-2 text-sm rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50"
                onClick={() => setShowConflictModal(false)}
                autoFocus
              >
                Cancel
              </button>
              <button
                className="px-4 py-2 text-sm rounded-md bg-[#6A0DAD] text-white hover:bg-[#5a0c94]"
                onClick={async () => {
                  setShowConflictModal(false);
                  await refreshSchedule();
                  toast.info('Week reloaded');
                }}
              >
                Refresh
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mobile day chips */}
      {isMobile && (
        <div className="mb-3 flex gap-2 overflow-x-auto">
          {weekDateInfo.map((d, i) => (
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
          weekDates={weekDateInfo}
          weekSchedule={weekSchedule}
          bookedSlots={bookedSlots}
          onScheduleChange={(s) => setWeekSchedule(s)}
          isMobile={isMobile}
          activeDayIndex={activeDay}
          onActiveDayChange={setActiveDay}
          timezone={userData?.timezone}
          startHour={startHour}
          endHour={endHour}
        />
      </div>


    </div>
  );
}
