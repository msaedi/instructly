'use client';

import WeekNavigator from '@/components/availability/WeekNavigator';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import Link from 'next/link';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { useAvailability } from '@/hooks/availability/useAvailability';
import { useBookedSlots } from '@/hooks/availability/useBookedSlots';
import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/queries/useAuth';
import { AVAILABILITY_CONSTANTS } from '@/types/availability';
import { UserData } from '@/types/user';
import { getWeekDates } from '@/lib/availability/dateHelpers';
import { Calendar, ArrowLeft } from 'lucide-react';
import { useEmbedded } from '../_embedded/EmbeddedContext';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';


function AvailabilityPageImpl() {
  const embedded = useEmbedded();
  const { user } = useAuth();
  const userData = user as unknown as UserData;
  const {
    currentWeekStart,
    weekSchedule,
    // hasUnsavedChanges, // autosave flow no longer uses this flag here
    isLoading,
    navigateWeek,
    setWeekSchedule,
    setMessage,
    message,
    refreshSchedule,
    version,
    lastModified,
    saveWeek,
    applyToFutureWeeks,
    goToCurrentWeek,
  } = useAvailability();

  const [activeDay, setActiveDay] = useState(0);
  const [repeatWeeks, setRepeatWeeks] = useState<number>(4);
  const [isMobile, setIsMobile] = useState(false);
  const [startHour, setStartHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_START_HOUR);
  const [endHour, setEndHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_END_HOUR);
  const [showConflictModal, setShowConflictModal] = useState(false);
  const [lastUpdatedLocal, setLastUpdatedLocal] = useState<string | null>(null);
  const [modalFocusTrap, setModalFocusTrap] = useState<HTMLDivElement | null>(null);
  const saveDebounceRef = useRef<number | null>(null);

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
      void fetchBookedSlots(currentWeekStart);
    }
  }, [currentWeekStart, isLoading, fetchBookedSlots]);

  // Saving indicator not used in the new autosave flow, keep for future use

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
    return undefined;
  }, [message, setMessage]);

  const header = useMemo(() => (
    <WeekNavigator
      currentWeekStart={currentWeekStart}
      onNavigate={navigateWeek}
      hasUnsavedChanges={false}
      showSubtitle={false}
      disabled={isLoading}
    />
  ), [currentWeekStart, navigateWeek, isLoading]);

  return (
    <div className="min-h-screen">
      {/* Header hidden when embedded */}
      {!embedded && (
        <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-4"><UserProfileDropdown /></div>
          </div>
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 hidden sm:block">
            <div className="container mx-auto px-8 lg:px-32 max-w-6xl pointer-events-none">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] pointer-events-auto">
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'max-w-none px-0 lg:px-0 py-0' : 'container mx-auto px-8 lg:px-32 py-8 max-w-6xl'}>
        {!embedded && (
          <div className="sm:hidden mb-2">
            <Link href="/instructor/dashboard" aria-label="Back to dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
              <ArrowLeft className="w-5 h-5" />
              <span className="sr-only">Back to dashboard</span>
            </Link>
          </div>
        )}
        {!embedded && (
          <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Calendar className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div>
                <h2 className="text-3xl font-bold text-gray-600 mb-2">Set Availability</h2>
                <p className="text-gray-600">Set the times you’re available to teach.</p>
              </div>
            </div>
          </div>
        )}

        <div id={embedded ? 'availability-first-card' : undefined} className="bg-white rounded-lg border border-gray-200 p-6">
        {header}

      {/* Tip below the week navigator */}
      <div className="mb-3 rounded-md border border-purple-100 bg-purple-50 px-3 py-2 relative">
        <p className="text-sm font-medium text-gray-800">Tip: Click any cell to mark yourself available</p>
        <p className="text-xs text-gray-700">Most instructors start with 10–15 hours/week</p>
        <p className="absolute bottom-2 right-3 text-[11px] text-gray-500">Last updated: <span>{lastUpdatedLocal || '—'}</span></p>
      </div>

      {/* Quick nav */}
      <div className="-mt-1 mb-2 flex items-center">
        <button
          type="button"
          onClick={() => {
            goToCurrentWeek();
          }}
          className="px-3 py-1 rounded-md border border-purple-200 bg-purple-50 text-[#7E22CE] text-sm hover:bg-purple-100"
        >
          Today
        </button>
      </div>

      {/* Actions (top of grid) */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* Repeat dropdown */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-700">Repeat this schedule:</span>
          <div className="relative inline-flex items-center">
            <Select value={String(repeatWeeks)} onValueChange={(v) => setRepeatWeeks(parseInt(v, 10))}>
              <SelectTrigger className="h-8 w-24 sm:w-28">
                <SelectValue placeholder="Repeat" />
              </SelectTrigger>
              <SelectContent>
                {[1,2,3,4,6,8,12].map((w) => (
                  <SelectItem key={w} value={String(w)}>{w} weeks</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

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
            // Immediately persist the current week as well to avoid unsaved banners during navigation
            try {
              const result = await saveWeek({ clearExisting: true, scheduleOverride: weekSchedule });
              if (!result.success) {
                if (result.code === 409) {
                  setShowConflictModal(true);
                } else {
                  toast.error(result.message || 'Failed to save availability');
                }
                return;
              }
            } catch {
              toast.error('Failed to save availability');
              return;
            }
            await refreshSchedule();
            setMessage(null);
          }}
          className="inline-flex items-center justify-center px-3 py-1 rounded-md text-white bg-[#7E22CE] hover:!bg-[#7E22CE] text-sm whitespace-nowrap"
        >
          Apply
        </button>

        {/* Hour range controls */}
        <div className="ml-auto flex items-center gap-2">
          <div className="flex flex-col leading-tight mr-1">
            <span className="text-sm text-gray-700">Teaching window</span>
            <span className="text-[11px] text-gray-500 -mt-0.5">Business Hours</span>
          </div>
          <div className="relative inline-flex items-center">
            <Select value={String(startHour)} onValueChange={(v) => {
              const sv = parseInt(v, 10);
              setStartHour(sv);
              if (sv >= endHour) setEndHour(Math.min(sv + 1, 23));
            }}>
              <SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Array.from({ length: 24 }, (_, h) => h).map((h) => (
                  <SelectItem key={h} value={String(h)}>{formatHour(h)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <span className="text-gray-500">to</span>
          <div className="relative inline-flex items-center">
            <Select value={String(endHour)} onValueChange={(v) => {
              const ev = parseInt(v, 10);
              setEndHour(ev);
              if (ev <= startHour) setStartHour(Math.max(ev - 1, 0));
            }}>
              <SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Array.from({ length: 24 }, (_, h) => h).map((h) => (
                  <SelectItem key={h} value={String(h)}>{formatHour(h)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
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
                className="px-4 py-2 text-sm rounded-md bg-[#7E22CE] text-white hover:bg-[#7E22CE]"
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
              className={`px-3 py-2 rounded-full text-sm border ${i === activeDay ? 'bg-[#7E22CE] text-white border-[#7E22CE]' : 'bg-white text-gray-700 border-gray-300'}`}
            >
              {d.date.toLocaleDateString('en-US', { weekday: 'short' })}
            </button>
          ))}
        </div>
      )}

      {/* Interactive Grid */}
      <div className="mt-2">
        <InteractiveGrid
          weekDates={weekDateInfo}
          weekSchedule={weekSchedule}
          bookedSlots={bookedSlots}
          onScheduleChange={(s) => {
            setWeekSchedule(s);
            if (typeof window !== 'undefined') {
              if (saveDebounceRef.current) window.clearTimeout(saveDebounceRef.current);
              saveDebounceRef.current = window.setTimeout(async () => {
                try {
                  const result = await saveWeek({ clearExisting: true, scheduleOverride: s });
                  if (!result.success) {
                    if (result.code === 409) {
                      setShowConflictModal(true);
                    } else {
                      toast.error(result.message || 'Failed to save availability');
                    }
                    return;
                  }
                  setMessage(null);
                } catch {
                  toast.error('Failed to save availability');
                }
              }, 700);
            }
          }}
          isMobile={isMobile}
          activeDayIndex={activeDay}
          onActiveDayChange={setActiveDay}
          {...(userData?.timezone && { timezone: userData.timezone })}
          startHour={startHour}
          endHour={endHour}
        />
      </div>
      </div>
      </div>
    </div>
  );
}

export default function InstructorAvailabilityPage() {
  return <AvailabilityPageImpl />;
}

// Do not export additional symbols from route module to satisfy Next page typing
