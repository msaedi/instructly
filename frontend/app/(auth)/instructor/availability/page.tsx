'use client';

import dynamic from 'next/dynamic';
import WeekNavigator from '@/components/availability/WeekNavigator';
import Link from 'next/link';
import { useAvailability } from '@/hooks/availability/useAvailability';
import { useBookedSlots } from '@/hooks/availability/useBookedSlots';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/hooks/queries/useAuth';
import { AVAILABILITY_CONSTANTS } from '@/types/availability';
import type { WeekBits } from '@/types/availability';
import { UserData } from '@/types/user';
import { getWeekDates } from '@/lib/availability/dateHelpers';
import { Calendar, ArrowLeft } from 'lucide-react';
import { useEmbedded } from '../_embedded/EmbeddedContext';
import { logger } from '@/lib/logger';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { useAvailabilityWeekInvalidation } from '@/features/instructor-profile/hooks/useAvailabilityWeekInvalidation';

const CalendarSkeleton = () => (
  <div className="space-y-2" aria-hidden="true">
    <Skeleton className="h-10 w-full" />
    <Skeleton className="h-[420px] w-full" />
  </div>
);

const WeekView = dynamic(() => import('@/components/calendar/WeekView'), {
  ssr: false,
  loading: () => <CalendarSkeleton />,
});

const UserProfileDropdown = dynamic(() => import('@/components/UserProfileDropdown'), {
  ssr: false,
  loading: () => <div className="h-10 w-10 rounded-full bg-gray-200 animate-pulse" aria-hidden="true" />,
});

const ConflictModal = dynamic(() => import('@/components/availability/ConflictModal'), {
  ssr: false,
  loading: () => null,
});

const LHCI = process.env['NEXT_PUBLIC_LH_CI'] === '1';
const autosaveEnv = process.env['NEXT_PUBLIC_AVAIL_AUTOSAVE']?.toLowerCase();
const AVAIL_AUTOSAVE_ENABLED = autosaveEnv === '1' || autosaveEnv === 'true';
const AUTOSAVE_DELAY_MS = 1200;
const refetchAfterSaveEnv = process.env['NEXT_PUBLIC_AVAILABILITY_REFETCH_AFTER_SAVE']?.toLowerCase();
const REFETCH_AFTER_SAVE = refetchAfterSaveEnv === '1' || refetchAfterSaveEnv === 'true';


function AvailabilityPageImpl() {
  const embedded = useEmbedded();
  const { user } = useAuth();
  const userData = user as unknown as UserData;
  const {
    currentWeekStart,
    weekBits,
    savedWeekBits,
    isLoading,
    navigateWeek,
    setWeekBits,
    setMessage,
    message,
    refreshSchedule,
    version,
    lastModified,
    saveWeek,
    applyToFutureWeeks,
    goToCurrentWeek,
    allowPastEdits,
  } = useAvailability();
  const currentWeekStartIso = currentWeekStart ? currentWeekStart.toISOString().split('T')[0] : undefined;
  const invalidateWeekSnapshot = useAvailabilityWeekInvalidation(userData?.id, currentWeekStartIso);

  const serializeBits = useCallback((bits: WeekBits) => {
    return Object.fromEntries(
      Object.entries(bits)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, dayBits]) => [date, Array.from(dayBits)])
    );
  }, []);

  const serializedWeekBits = useMemo(
    () => JSON.stringify(serializeBits(weekBits)),
    [serializeBits, weekBits]
  );
  const serializedSavedWeekBits = useMemo(
    () => JSON.stringify(serializeBits(savedWeekBits)),
    [serializeBits, savedWeekBits]
  );
  const hasPendingChanges = serializedWeekBits !== serializedSavedWeekBits;

  const [activeDay, setActiveDay] = useState(0);
  const [repeatWeeks, setRepeatWeeks] = useState<number>(4);
  const [isMobile, setIsMobile] = useState(false);
  const [startHour, setStartHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_START_HOUR);
  const [endHour, setEndHour] = useState<number>(AVAILABILITY_CONSTANTS.DEFAULT_END_HOUR);
  const [lastUpdatedLocal, setLastUpdatedLocal] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [conflictState, setConflictState] = useState<{ serverVersion?: string } | null>(null);
  const [isConflictRefreshing, setIsConflictRefreshing] = useState(false);
  const [isConflictOverwriting, setIsConflictOverwriting] = useState(false);
  const autosaveTimer = useRef<number | null>(null);
  const autosaveEnabled = AVAIL_AUTOSAVE_ENABLED;

  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return;
    if (typeof window === 'undefined') return;
    const legacyPath = '/instructors/availability?';
    const originalFetch = window.fetch;
    const patched: typeof window.fetch = (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : typeof Request !== 'undefined' && input instanceof Request
              ? input.url
              : undefined;
      if (typeof url === 'string' && url.includes(legacyPath)) {
        logger.warn('[availability-editor] Detected legacy availability fetch', { url });
      }
      return originalFetch(input, init);
    };

    window.fetch = patched;
    return () => {
      window.fetch = originalFetch;
    };
  }, []);

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


  function formatHour(h: number): string {
    if (h === 24) {
      return '12:00 AM (+1d)';
    }
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

  useEffect(() => {
    if (!message) return;
    if (message.type === 'error') {
      toast.error(message.text, {
        description: 'Please try again or refresh.',
        action: {
          label: 'Retry',
          onClick: () => {
            void refreshSchedule();
          },
        },
      });
    } else if (message.type === 'success') {
      toast.success(message.text);
    } else {
      toast(message.text);
    }
  }, [message, refreshSchedule]);

  const handleBitsChange = useCallback((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
    setWeekBits(next);
    setMessage(null);
  }, [setWeekBits, setMessage]);

  const handleDiscardChanges = useCallback(() => {
    setWeekBits(savedWeekBits);
    setMessage(null);
    setConflictState(null);
    toast.info('Reverted to last saved schedule.');
  }, [savedWeekBits, setWeekBits, setMessage]);

  const persistWeek = useCallback(
    async ({ override = false }: { override?: boolean } = {}) => {
      setIsSaving(true);
      try {
        const result = await saveWeek({
          clearExisting: true,
          override,
        });

        if (!result.success) {
          if (result.code === 409) {
            const nextState = result.serverVersion ? { serverVersion: result.serverVersion } : {};
            setConflictState(nextState);
            toast.warning('Week availability changed in another session. Choose how to proceed.');
          } else {
            toast.error(result.message || 'Failed to save availability');
          }
          return false;
        }

        toast.success(result.message || 'Availability saved');

        if (REFETCH_AFTER_SAVE) {
          try {
            await refreshSchedule();
            setMessage(null);
          } catch {
            toast.error('Saved, but failed to refresh the latest schedule.');
          }
        } else {
          logger.debug('Refetch after save disabled; retaining current week snapshot');
          setMessage(null);
        }

        setConflictState(null);
        try {
          await invalidateWeekSnapshot();
        } catch (error) {
          logger.warn('Failed to invalidate availability snapshot after save', error as Error);
        }
        return true;
      } finally {
        setIsSaving(false);
      }
    },
    [saveWeek, refreshSchedule, setMessage, invalidateWeekSnapshot]
  );

  const handleSaveWeek = useCallback(() => {
    void persistWeek();
  }, [persistWeek]);

  const handleConflictRefresh = useCallback(async () => {
    setIsConflictRefreshing(true);
    try {
      await refreshSchedule();
      setMessage(null);
      setConflictState(null);
      toast.info('Week reloaded');
    } catch {
      toast.error('Failed to refresh the latest schedule.');
    } finally {
      setIsConflictRefreshing(false);
    }
  }, [refreshSchedule, setMessage]);

  const handleConflictOverwrite = useCallback(async () => {
    setIsConflictOverwriting(true);
    const success = await persistWeek({ override: true });
    if (success) {
      setConflictState(null);
    }
    setIsConflictOverwriting(false);
  }, [persistWeek]);

  useEffect(() => {
    if (!autosaveEnabled || typeof window === 'undefined') {
      return;
    }
    if (!hasPendingChanges || isLoading || isSaving || conflictState) {
      if (autosaveTimer.current) {
        window.clearTimeout(autosaveTimer.current);
        autosaveTimer.current = null;
      }
      return;
    }

    if (autosaveTimer.current) {
      window.clearTimeout(autosaveTimer.current);
    }

    autosaveTimer.current = window.setTimeout(() => {
      autosaveTimer.current = null;
      void persistWeek();
    }, AUTOSAVE_DELAY_MS);

    return () => {
      if (autosaveTimer.current) {
        window.clearTimeout(autosaveTimer.current);
        autosaveTimer.current = null;
      }
    };
  }, [autosaveEnabled, conflictState, hasPendingChanges, isLoading, isSaving, persistWeek]);

  const header = useMemo(() => (
    <WeekNavigator
      currentWeekStart={currentWeekStart}
      onNavigate={navigateWeek}
      hasUnsavedChanges={hasPendingChanges}
      showSubtitle={false}
      disabled={isLoading}
    />
  ), [currentWeekStart, navigateWeek, isLoading, hasPendingChanges]);

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
        <SectionHeroCard
          id={embedded ? 'availability-first-card' : undefined}
          icon={Calendar}
          title="Availability"
          subtitle="Map out the days and hours you’re available so students can book the right times."
        />

        <div className="bg-white rounded-lg border border-gray-200 p-6">
        {header}

      {/* Tip below the week navigator */}
      <div className="mb-3 rounded-md border border-purple-100 bg-purple-50 px-3 py-2 relative">
        <p className="text-sm font-medium text-gray-800">Tip: Click any cell to mark yourself available</p>
        <p className="text-xs text-gray-700">Most instructors start with 10–15 hours/week</p>
        <p className="hidden sm:block absolute bottom-2 right-3 text-[11px] text-gray-500">
          Last updated: <span>{lastUpdatedLocal || '—'}</span>
        </p>
      </div>

      {/* Actions (top of grid) */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* Repeat dropdown */}
        <div className="flex items-center gap-2 w-full sm:w-auto flex-nowrap overflow-hidden">
          <span className="text-xs sm:text-sm text-gray-700 whitespace-nowrap flex-shrink-0">Repeat this schedule:</span>
          <div className="flex items-center flex-1 gap-1 sm:gap-2 min-w-0">
            <div className="repeat-schedule-select relative inline-flex items-center flex-grow-0 basis-[22%] max-w-[90px] min-w-[64px] sm:flex-none sm:max-w-none sm:w-auto sm:min-w-[120px] sm:w-28 order-1">
              <Select value={String(repeatWeeks)} onValueChange={(v) => setRepeatWeeks(parseInt(v, 10))}>
                <SelectTrigger className="h-7 sm:h-9 w-full px-2 sm:px-3 text-xs sm:text-sm text-center whitespace-nowrap" hideIconOnMobile>
                  <SelectValue placeholder="Repeat" />
                </SelectTrigger>
                <SelectContent>
                  {[1,2,3,4,6,8,12].map((w) => (
                    <SelectItem key={w} value={String(w)}>
                      {w} week{w === 1 ? '' : 's'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="repeat-schedule-select relative inline-flex items-center flex-grow-0 basis-[22%] max-w-[90px] min-w-[64px] sm:flex-none sm:max-w-none sm:w-auto sm:min-w-[120px] sm:w-28 order-2">
              <button
                className="repeat-schedule-apply w-full inline-flex items-center justify-center h-7 sm:h-9 px-2 sm:px-3 rounded-md bg-[#7E22CE] text-white text-xs sm:text-sm font-medium whitespace-nowrap shadow-sm hover:!bg-[#7E22CE] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#C084FC]"
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
                  const persisted = await persistWeek();
                  if (!persisted) return;
                }}
              >
                Apply
              </button>
            </div>
          </div>
        </div>

        {/* Hour range controls */}
        <div className="w-full">
          <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
            <div className="flex w-full flex-nowrap items-center gap-1 overflow-x-auto sm:w-auto sm:gap-2">
              <div className="flex flex-row items-center gap-2 text-xs text-gray-700 whitespace-nowrap flex-shrink-0 sm:flex-col sm:items-start sm:gap-0 sm:text-sm">
                <span>Teaching window:</span>
                <span className="text-[11px] text-gray-500 hidden sm:block -mt-0.5">Business Hours</span>
              </div>
              <div className="ml-auto flex items-center gap-1 text-xs text-gray-700 flex-shrink-0 sm:ml-0 sm:gap-2 sm:text-sm">
                <div className="relative inline-flex items-center w-[72px] sm:w-auto">
                  <Select
                    value={String(startHour)}
                    onValueChange={(v) => {
                      const sv = parseInt(v, 10);
                      setStartHour(sv);
                      if (sv >= endHour) setEndHour(Math.min(sv + 1, 24));
                    }}
                  >
                    <SelectTrigger className="h-7 sm:h-9 w-full sm:w-28 px-1 text-[11px] sm:px-3 sm:text-sm justify-center" hideIconOnMobile>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 24 }, (_, h) => h).map((h) => (
                        <SelectItem key={h} value={String(h)}>
                          {formatHour(h)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <span className="whitespace-nowrap text-gray-700">to</span>
                <div className="relative inline-flex items-center w-[72px] sm:w-auto">
                  <Select
                    value={String(endHour)}
                    onValueChange={(v) => {
                      const ev = parseInt(v, 10);
                      setEndHour(ev);
                      if (ev <= startHour) setStartHour(Math.max(ev - 1, 0));
                    }}
                  >
                    <SelectTrigger className="h-7 sm:h-9 w-full sm:w-28 px-1 text-[11px] sm:px-3 sm:text-sm justify-center" hideIconOnMobile>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 24 }, (_, h) => h + 1).map((h) => (
                        <SelectItem key={h} value={String(h)}>
                          {formatHour(h)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ConflictModal
        open={Boolean(conflictState)}
        onClose={() => setConflictState(null)}
        onRefresh={handleConflictRefresh}
        onOverwrite={handleConflictOverwrite}
        isRefreshing={isConflictRefreshing}
        isOverwriting={isConflictOverwriting}
        {...(conflictState?.serverVersion
          ? { serverVersion: conflictState.serverVersion }
          : {})}
      />

      {/* Mobile day chips */}
      {isMobile && (
        <div className="mb-3 grid grid-cols-7 gap-1 w-full">
          {weekDateInfo.map((d, i) => (
            <button
              key={d.fullDate}
              onClick={() => setActiveDay(i)}
              className={`w-full px-1.5 py-2 rounded-full text-xs font-medium border text-center ${
                i === activeDay ? 'bg-[#7E22CE] text-white border-[#7E22CE]' : 'bg-white text-gray-700 border-gray-300'
              }`}
            >
              {d.date.toLocaleDateString('en-US', { weekday: 'short' })}
            </button>
          ))}
        </div>
      )}

      {/* Interactive Grid */}
      {allowPastEdits === false && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          Past-day changes are ignored on save.
        </div>
      )}
      <div className="mt-2">
        {LHCI ? (
          <div
            data-testid="lhci-availability-skeleton"
            style={{ height: 720 }}
            className="flex flex-col"
          >
            <CalendarSkeleton />
          </div>
        ) : isLoading ? (
          <CalendarSkeleton />
        ) : (
          <WeekView
            weekDates={weekDateInfo}
            weekBits={weekBits}
            bookedSlots={bookedSlots}
            onBitsChange={handleBitsChange}
            isMobile={isMobile}
            activeDayIndex={activeDay}
            onActiveDayChange={setActiveDay}
            {...(userData?.timezone && { timezone: userData.timezone })}
            startHour={startHour}
            endHour={endHour}
            allowPastEditing={allowPastEdits === true}
            onTodayClick={goToCurrentWeek}
          />
        )}
      </div>
      <div className="pb-16" />
    </div>
    {hasPendingChanges && (
      <div className="fixed bottom-4 left-1/2 z-40 w-full max-w-3xl -translate-x-1/2 px-4">
        <div className="flex items-center justify-between gap-4 rounded-full border border-gray-200 bg-white px-6 py-3 shadow-lg">
          <div className="text-sm text-gray-800">
            <div className="font-medium">Unsaved changes</div>
            <div className="text-xs text-gray-500">Past-day edits are historical and included in copies.</div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleDiscardChanges}
              className="rounded-full border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={handleSaveWeek}
              disabled={isSaving || !hasPendingChanges}
              className="rounded-full bg-[#7E22CE] px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#6b1ebe] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSaving ? 'Saving…' : 'Save Week'}
            </button>
          </div>
        </div>
      </div>
    )}
  </div>
</div>
);
}

export default function InstructorAvailabilityPage() {
  return <AvailabilityPageImpl />;
}

// Do not export additional symbols from route module to satisfy Next page typing
