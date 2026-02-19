'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useLessonDetails } from '@/hooks/useMyLessons';
import { useJoinLesson, useVideoSessionStatus } from '@/hooks/queries/useLessonRoom';
import { PreLessonWaiting } from '@/components/lessons/video/PreLessonWaiting';
import { ActiveLesson } from '@/components/lessons/video/ActiveLesson';
import { NotJoinable, type NotJoinableReason } from '@/components/lessons/video/NotJoinable';
import { LessonEnded } from '@/components/lessons/video/LessonEnded';
import type { Booking } from '@/features/shared/api/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type RoomPhase =
  | 'loading'
  | 'pre-lesson'
  | 'joining'
  | 'active'
  | 'ended'
  | 'not-joinable';

interface PhaseResult {
  phase: RoomPhase;
  notJoinableReason: NotJoinableReason | null;
}

// ---------------------------------------------------------------------------
// Phase detection
// ---------------------------------------------------------------------------

function determineInitialPhase(booking: Booking): PhaseResult {
  if (booking.location_type !== 'online') {
    return { phase: 'not-joinable', notJoinableReason: 'in-person' };
  }
  if (booking.status === 'CANCELLED') {
    return { phase: 'not-joinable', notJoinableReason: 'cancelled' };
  }
  if (booking.video_session_ended_at) {
    return { phase: 'ended', notJoinableReason: null };
  }
  if (booking.status !== 'CONFIRMED' || !booking.join_opens_at) {
    return { phase: 'not-joinable', notJoinableReason: 'not-available' };
  }
  return { phase: 'pre-lesson', notJoinableReason: null };
}

// ---------------------------------------------------------------------------
// Shell (header wrapper for non-active states)
// ---------------------------------------------------------------------------

function LessonRoomShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">
              iNSTAiNSTRU
            </h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-4">{children}</main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LessonRoomPage() {
  const params = useParams();
  const rawBookingId = params['bookingId'];
  const bookingId = typeof rawBookingId === 'string' ? rawBookingId : '';

  // Auth
  const { user, isLoading: authLoading, isAuthenticated, redirectToLogin } = useAuth();

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      redirectToLogin();
    }
  }, [authLoading, isAuthenticated, redirectToLogin]);

  // Booking data
  const { data: booking, isLoading: bookingLoading, error: bookingError } = useLessonDetails(bookingId);

  // Derived phase from booking data (pure computation, no effect)
  const bookingPhase = useMemo((): PhaseResult => {
    if (!booking) return { phase: 'loading', notJoinableReason: null };
    return determineInitialPhase(booking);
  }, [booking]);

  // User-initiated phase override (joining → active → ended)
  const [phaseOverride, setPhaseOverride] = useState<RoomPhase | null>(null);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);

  // Resolved phase: user override wins when set, otherwise derived from booking
  const rawPhase: RoomPhase = phaseOverride ?? bookingPhase.phase;
  const notJoinableReason = bookingPhase.notJoinableReason;

  // Join / leave handlers
  const { joinLesson, isPending: isJoining } = useJoinLesson();

  const handleJoin = async () => {
    setJoinError(null);
    setPhaseOverride('joining');
    try {
      const response = await joinLesson(bookingId);
      setAuthToken(response.auth_token);
      setPhaseOverride('active');
    } catch (err: unknown) {
      setPhaseOverride(null); // fall back to derived phase
      const message = err instanceof Error ? err.message : 'Failed to join lesson';
      setJoinError(message);
    }
  };

  const handleLeave = () => {
    setPhaseOverride('ended');
  };

  // Phase-0 determination (M5): polling keyed only to rawPhase can continue
  // indefinitely after session_ended_at is observed.
  // Video session polling (active + ended; no continuous poll once ended)
  const { sessionData } = useVideoSessionStatus(bookingId, {
    enabled: rawPhase === 'active' || rawPhase === 'ended',
    ...(rawPhase === 'active' && { pollingIntervalMs: 10_000 }),
    stopPollingWhenEnded: true,
  });

  // Final phase: transition active→ended when poll detects session close (derived, no effect)
  const phase: RoomPhase =
    rawPhase === 'active' && sessionData?.session_ended_at ? 'ended' : rawPhase;

  // Derived user info
  const userRole: 'student' | 'instructor' =
    booking && user && booking.instructor_id === user.id ? 'instructor' : 'student';
  const userName = user ? `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim() : '';
  const otherPartyName =
    userRole === 'student'
      ? booking?.instructor?.first_name ?? 'Instructor'
      : booking?.student?.first_name ?? 'Student';
  const otherPartyRole: 'student' | 'instructor' = userRole === 'student' ? 'instructor' : 'student';
  const fallbackPath = userRole === 'instructor' ? '/instructor/bookings' : '/student/lessons';

  // ---- Render ----

  // Active lesson: full-screen, no shell
  if (phase === 'active' && authToken && user) {
    return (
      <ActiveLesson
        authToken={authToken}
        userName={userName}
        userId={user.id}
        onLeave={handleLeave}
        fallbackPath={fallbackPath}
      />
    );
  }

  // Everything else is wrapped in the shell
  if (authLoading || bookingLoading) {
    return (
      <LessonRoomShell>
        <div className="flex items-center justify-center py-24">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      </LessonRoomShell>
    );
  }

  if (bookingError || !booking) {
    const isInstructor = user?.roles?.includes('INSTRUCTOR') ?? false;
    const lessonsPath = isInstructor ? '/instructor/bookings' : '/student/lessons';
    return (
      <LessonRoomShell>
        <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
          <p className="text-destructive">
            {bookingError ? 'Failed to load lesson details.' : 'Lesson not found.'}
          </p>
          <Link
            href={lessonsPath}
            className="text-sm text-primary underline"
          >
            Back to My Lessons
          </Link>
        </div>
      </LessonRoomShell>
    );
  }

  if (phase === 'not-joinable' && notJoinableReason) {
    return (
      <LessonRoomShell>
        <NotJoinable reason={notJoinableReason} userRole={userRole} />
      </LessonRoomShell>
    );
  }

  if (phase === 'ended') {
    return (
      <LessonRoomShell>
        <LessonEnded booking={booking} sessionData={sessionData} userRole={userRole} />
      </LessonRoomShell>
    );
  }

  // Pre-lesson / joining
  return (
    <LessonRoomShell>
      <PreLessonWaiting
        booking={booking}
        userName={userName}
        otherPartyName={otherPartyName}
        otherPartyRole={otherPartyRole}
        onJoin={handleJoin}
        isJoining={isJoining || phase === 'joining'}
        joinError={joinError}
      />
    </LessonRoomShell>
  );
}
