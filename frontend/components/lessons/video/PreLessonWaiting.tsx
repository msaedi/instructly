'use client';

import { useCountdown } from '@/hooks/useCountdown';
import type { Booking } from '@/features/shared/api/types';

interface PreLessonWaitingProps {
  booking: Booking;
  userName: string;
  otherPartyName: string;
  otherPartyRole: 'student' | 'instructor';
  onJoin: () => void;
  isJoining: boolean;
  joinError: string | null;
}

export function PreLessonWaiting({
  booking,
  userName,
  otherPartyName,
  otherPartyRole,
  onJoin,
  isJoining,
  joinError,
}: PreLessonWaitingProps) {
  const opensCountdown = useCountdown(booking.join_opens_at ?? null);
  const closesCountdown = useCountdown(booking.join_closes_at ?? null);

  const windowOpen = opensCountdown.isExpired && !closesCountdown.isExpired;
  const windowClosed = opensCountdown.isExpired && closesCountdown.isExpired;

  return (
    <div className="flex flex-col items-center justify-center gap-6 py-12 px-4 text-center">
      <h1 className="text-2xl font-semibold">{booking.service_name}</h1>

      <p className="text-muted-foreground">
        {otherPartyRole === 'instructor'
          ? `Your instructor: ${otherPartyName}`
          : `Your student: ${otherPartyName}`}
      </p>

      {!opensCountdown.isExpired && (
        <div className="flex flex-col items-center gap-2">
          <p className="text-sm text-muted-foreground">Join opens in</p>
          <p className="text-4xl font-mono font-bold tabular-nums">
            {opensCountdown.formatted}
          </p>
        </div>
      )}

      {windowOpen && !isJoining && (
        <div className="flex flex-col items-center gap-2">
          <p className="text-sm text-muted-foreground">
            Window closes in {closesCountdown.formatted}
          </p>
          <button
            type="button"
            onClick={onJoin}
            className="rounded-lg bg-primary px-8 py-3 text-lg font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Join Lesson
          </button>
        </div>
      )}

      {isJoining && (
        <div className="flex flex-col items-center gap-2">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-muted-foreground">Connecting...</p>
        </div>
      )}

      {windowClosed && (
        <p className="text-sm text-destructive font-medium">
          Join window has closed.
        </p>
      )}

      {joinError && (
        <p className="text-sm text-destructive" role="alert">
          {joinError}
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        Joining as {userName}
      </p>
    </div>
  );
}
